# Usage
# python3 webstreaming.py

# import the necessary packages
from decode_nfce import DecodeNFCe
from imutils.video import VideoStream
from flask import Response
from flask import Flask
from flask import render_template
from flask import redirect, url_for, request, flash, send_file
import threading
import argparse
import datetime
import imutils
import time
import cv2
from pyzbar import pyzbar
import re
import requests
import pandas as pd
import numpy as np
import base64
import os

import warnings
warnings.filterwarnings("ignore")

nfce = DecodeNFCe()
found = set()
regex_chave = "p=(\\d{44})"
path_csv_coupons = "./data/coupons.csv"
path_image_file = "./data/"
columns = ['Data_Emissao',  'Descricao_Prod', 'Qtd', 'Unid_Med',
			'Valores_Unit','Valor_Total_Prod', 'Valor_Total_NF',
			'Codigo_NCM_Prod', 'NCM_Descricao', 'Estabelecimento_CNPJ',
       		'Estabelecimento',  'Chave']
data = pd.DataFrame(columns=columns)
titleWeb = "QRCode Detector"
logList = []

# initialize the output frame and a lock used to ensure thread-safe
# exchanges of the output frames (useful for multiple browsers/tabs
# are viewing the stream)
outputFrame = None
lock = threading.Lock()

# initialize a flask object
app = Flask(__name__)

# initialize the video stream and allow the camera sensor to
# warmup
#vs = VideoStream(usePiCamera=1).start()
vs = VideoStream(src=0).start()
time.sleep(2.0)

@app.route("/")
def index():
	# return the rendered template
	return render_template('index.html',  
							tables=[data.to_html(classes='tableData table table-striped ')], 
							titles=data.columns.values,
							titulo=titleWeb)
	#return render_template("index.html", data_columns=columns)

def detect_from_video():
	# grab global references to the video stream, output frame, and
	# lock variables
	global vs, outputFrame, lock, data, found

	if os.path.exists(path_csv_coupons):
		data = pd.read_csv(path_csv_coupons)
	else:
		data = pd.DataFrame(columns=columns)

	found = set(data['Chave'])
	
	# loop over frames from the video stream
	while True:
		# read the next frame from the video stream
		frame = vs.read()

		# call function for find barcodes and process the decode NFCe
		detect_qrcode("video", frame)

		time.sleep(0.05)
		
		
def detect_qrcode(origin, frame):
	text = ""
	color = (255, 0, 0)
	global outputFrame

	#Resize frame
	frame = imutils.resize(frame, width=400)
	# find the barcodes in the frame and decode each of the barcodes
	barcodes = pyzbar.decode(frame)

	# loop over the detected barcodes
	if barcodes:
		for barcode in barcodes:
			
			# the barcode data is a bytes object so if we want to draw it
			# on our output image we need to convert it to a string first
			barcodeData = barcode.data.decode("utf-8")
			barcodeType = barcode.type

			#Extract key of NFCe from QRCode URL
			chave = re.findall(regex_chave, barcodeData)
			#Checking if was found a valid key
			if chave:
				chave = chave[0]
				if chave not in found:
					text = "{} ({})".format(barcodeData, barcodeType)
					color = (255, 0 , 0)

					found.add(chave)
					
					#Create a new Thread to run the function get data from Sefaz Server
					dec = threading.Thread(target=decodeNF, args=(chave,))
					dec.daemon = True
					dec.start()
					chave = []
				else:
					if (origin == "photo"):
						addLog("[INFO] Nota {} já armazenada no arquivo!".format(chave))
						chave = []
					else:
						text = "Nota armazenada no arquivo!"
						color = (0, 255 , 0)

			# extract the bounding box location of the barcode and draw
			# the bounding box surrounding the barcode on the image
			(x, y, w, h) = barcode.rect
			cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

			# draw the barcode data and barcode type on the image
			cv2.putText(frame, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

			if (origin == "video"):
				with lock:
					outputFrame = frame.copy()
			else:
				return frame

			
	
	elif (origin == "video"):
		with lock:
			outputFrame = frame.copy()
	else:
		return frame

@app.route('/detect_image', methods=['POST'])
def detect_image():
	if 'fileImage' not in request.files:
		addLog("[ERROR] File not found in request")
		return Response(status=500)
	else:
		image = request.files['fileImage']
		if image.filename == '':
			addLog('[ERROR] No selected file')
			return Response(status=500)
		else:
			imageUpload = cv2.imdecode(np.fromstring(image.read(), np.uint8), cv2.IMREAD_UNCHANGED)
			
			# call function for find barcodes and process the decode NFCe
			frame = detect_qrcode("photo", imageUpload)
			(flag, encodedImage) = cv2.imencode(".jpg", frame)
			
			return app.response_class(base64.b64encode(encodedImage.tobytes()), mimetype='text/html')


def decodeNF(chave, tryCount=1):
	global found, data, nfce
	addLog("[INFO] Connecting to NFCe URL ... Key: {}".format(chave))
					
	url = "https://www.sefaz.rs.gov.br/ASP/AAE_ROOT/NFE/SAT-WEB-NFE-COM_2.asp?chaveNFe={}&HML=false&NFFCBA06010".format(chave)

	#Connect to the NFCe page URL and get the data
	page = requests.post(url)
		
	#Test if the request page was successfully
	if page.status_code == 200:
		addLog("[INFO] Decoding data ...")
		new_data = nfce.get_data(page, chave, columns)
		data = pd.concat([data, new_data], axis=0, ignore_index=True)
		#Save data in file
		addLog("[INFO] Saving file on disc ...")
		data.to_csv(path_csv_coupons, index=False)
	else:
		addLog("[ERROR] Problem with connecting to the page of Sefaz: {}".format(page.status_code))
		if( tryCount < 4):
			addLog("[INFO] Trying to connect again, try count {}".format(tryCount))
			decodeNF(chave, tryCount + 1)
		else:
			addLog("[ERROR] Could not connect to server SEFAZ, try in few minutes . . .")
			found.remove(chave)
		
		
def generate():
	# grab global references to the output frame and lock variables
	global outputFrame, lock

	# loop over frames from the output stream
	while True:
		# wait until the lock is acquired
		with lock:
			# check if the output frame is available, otherwise skip
			# the iteration of the loop
			if outputFrame is None:
				continue

			# encode the frame in JPEG format
			(flag, encodedImage) = cv2.imencode(".jpg", outputFrame)

			# ensure the frame was successfully encoded
			if not flag:
				continue

		# yield the output frame in the byte format
		yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 	bytearray(encodedImage) + b'\r\n')

@app.route("/video_feed")
def video_feed():
	# return the response generated along with the specific media
	# type (mime type)
	return Response(generate(), mimetype = "multipart/x-mixed-replace; boundary=frame")

@app.route('/logStream')
def logStream():
	def generate_log():
		global data
		#with open('job.log') as f:
		while True:
			#yield f.read()
			for log in logList:
				tag_resp = "<p> "+ logList.pop(0) +"</p>"
				yield tag_resp
			time.sleep(1)

	return app.response_class(generate_log(), mimetype='text/html')

def addLog(log):
	print(log)
	logTime = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
	log = "{} : {}".format(logTime, log )
	logList.append(log)


# check to see if this is the main thread of execution
if __name__ == '__main__':
	# construct the argument parser and parse command line arguments
	#ap = argparse.ArgumentParser()
	#ap.add_argument("-i", "--ip", type=str, required=True, help="ip address of the device")
	#ap.add_argument("-o", "--port", type=int, required=True, help="ephemeral port number of the server (1024 to 65535)")
	#args = vars(ap.parse_args())

	# start a thread that will perform QRCode detection
	t = threading.Thread(target=detect_from_video)
	t.daemon = True
	t.start()

	# start the flask app
	#app.run(host=args["ip"], port=args["port"], debug=True, threaded=True, use_reloader=False)
	app.run(debug=True, threaded=True, use_reloader=False)

# release the video stream pointer
vs.stop()