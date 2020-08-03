# USAGE
# python webstreaming.py --ip 0.0.0.0 --port 8000

# import the necessary packages
from decode_nfce import DecodeNFCe
from imutils.video import VideoStream
from flask import Response
from flask import Flask
from flask import render_template
from flask import redirect, url_for
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
import os

import warnings
warnings.filterwarnings("ignore")

nfce = DecodeNFCe()
found = set()
regex_chave = "p=(\\d{44})"
path_csv_coupons = "./data/coupons.csv"
columns = ['Data_Emissao',  'Descricao_Prod', 'Qtd', 'Unid_Med',
			'Valores_Unit','Valor_Total_Prod', 'Valor_Total_NF',
			'Codigo_NCM_Prod', 'NCM_Descricao', 'Estabelecimento_CNPJ',
       		'Estabelecimento',  'Chave']
data = pd.DataFrame(columns=columns)

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
							titulo="WebCam QRCode Detector")
	#return render_template("index.html", data_columns=columns)

def detect_image():
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
		# read the next frame from the video stream, resize it,
		# convert the frame to grayscale, and blur it
		frame = vs.read()
		frame = imutils.resize(frame, width=400)

		# find the barcodes in the frame and decode each of the barcodes
		barcodes = pyzbar.decode(frame)

		# loop over the detected barcodes
		if len(barcodes) > 0:
			for barcode in barcodes:
				# extract the bounding box location of the barcode and draw
				# the bounding box surrounding the barcode on the image
				(x, y, w, h) = barcode.rect
				cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
				# the barcode data is a bytes object so if we want to draw it
				# on our output image we need to convert it to a string first
				barcodeData = barcode.data.decode("utf-8")
				barcodeType = barcode.type
				
				# draw the barcode data and barcode type on the image
				text = "{} ({})".format(barcodeData, barcodeType)
				cv2.putText(frame, text, (x, y - 10),
					cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

				with lock:
					outputFrame = frame.copy()
				
				#Extract key of NFCe from QRCode URL
				chave = re.findall(regex_chave, barcodeData)
				#Checking if was found a valid key
				if len(chave) > 0:
					chave = chave[0]
					if chave not in found:
						found.add(chave)
						
						#Create a new Thread to run the function get data from Sefaz Server
						dec = threading.Thread(target=decodeNF, args=(chave,))
						dec.daemon = True
						dec.start()
		else:
			with lock:
				outputFrame = frame.copy()


def decodeNF(chave, tryCount=1):
	global found, data, nfce
	print("[INFO] Connecting to NFCe URL ... Key:", chave)
					
	url = "https://www.sefaz.rs.gov.br/ASP/AAE_ROOT/NFE/SAT-WEB-NFE-COM_2.asp?chaveNFe="+ chave +"&HML=false&NFFCBA06010"

	#Connect to the NFCe page URL and get the data
	page = requests.post(url)
		
	#Test if the request page was successfully
	if page.status_code == 200:
		new_data = nfce.get_data(page, chave, columns)
		data = pd.concat([data, new_data], axis=0, ignore_index=True)
		#Save data in file
		print("[INFO] Saving file on disc ...")
		data.to_csv(path_csv_coupons, index=False)
	else:
		print("[ERROR] Problem with connecting to the page of Sefaz: ", page.status_code)
		if( tryCount < 4):
			print("[INFO] Trying to connect again, try count ", tryCount)
			decodeNF(chave, tryCount + 1)
		else:
			print("[ERROR] Could not connect to server SEFAZ, try in few minutes . . .")
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


# check to see if this is the main thread of execution
if __name__ == '__main__':
	# construct the argument parser and parse command line arguments
	ap = argparse.ArgumentParser()
	ap.add_argument("-i", "--ip", type=str, required=True, help="ip address of the device")
	ap.add_argument("-o", "--port", type=int, required=True, help="ephemeral port number of the server (1024 to 65535)")
	args = vars(ap.parse_args())

	# start a thread that will perform QRCode detection
	t = threading.Thread(target=detect_image)
	t.daemon = True
	t.start()

	# start the flask app
	app.run(host=args["ip"], port=args["port"], debug=True, threaded=True, use_reloader=False)

# release the video stream pointer
vs.stop()