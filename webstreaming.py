# import the necessary packages
from decode_nfce import DecodeNFCe
from decode_nfce import GoogleSpreadSheet
from imutils.video import VideoStream
from flask import Response, Flask, render_template, redirect, url_for, request, flash, send_file
import threading
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
import json

import warnings
warnings.filterwarnings("ignore")

#Open and read the JSON config file
json_file = open('./config/config.json')
config_options = json.load(json_file)
json_file.close()

#Create global objects to decode and save coupons data
nfce = DecodeNFCe()

#Create a object to save data on Google Spreadsheet
google_sheet = GoogleSpreadSheet(scope_sheets=config_options['scope_sheets'],
									path_credentials=config_options['path_credentials'],
									spreadsheet_key=config_options['spreadsheet_key'])

#Set object used to verify if the coupons already exists on database or csv file
keys_found_set = set()
#Regex expression to extract the coupon key from URL detected in the image
regex_chave = "p=(\\d{44})"
#Path to files on local machine
path_csv_coupons = "./data/coupons.csv"
path_image_file = "./data/"
#List of columns used to create the CSV file or to insert in the database table
columns_coupons = ['dt_emissao',  'de_produto', 'qt_produto', 'no_unidade_medida',
			'vr_unitario','vr_total_produto', 'vr_total_NF',
			'co_NCM_produto', 'de_NCM_produto', 'nu_cnpj_estabelecimento',
       		'no_estabelecimento',  'nu_chave']
#DataFrame with all coupons
df_coupons = pd.DataFrame(columns=columns_coupons)
titleWeb = "QRCode Detector"
logList = []

# initialize the output frame and a lock used to ensure thread-safe
# exchanges of the output frames (useful for multiple browsers/tabs
# are viewing the stream)
outputFrame = None
lock = threading.Lock()

# initialize a flask object
app = Flask(__name__)

# initialize the video stream and allow the camera sensor to warmup
#vs = VideoStream(usePiCamera=1).start()
vs = VideoStream(src=0).start()
time.sleep(2.0)

@app.route("/")
def index():
	# return the rendered template
	return render_template('index.html',  
							tables=[df_coupons.to_html(classes='tableData table table-striped ')], 
							titles=df_coupons.columns.values,
							titulo=titleWeb)
	#return render_template("index.html", data_columns=columns)

def detect_from_video():
	# grab global references to the video stream, output frame, and
	# lock variables
	global vs, outputFrame, lock, df_coupons, keys_found_set

	if os.path.exists(path_csv_coupons):
		df_coupons = pd.read_csv(path_csv_coupons)
	else:
		df_coupons = pd.DataFrame(columns=columns_coupons)

	keys_found_set = set(df_coupons['nu_chave'])
	
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
				if chave not in keys_found_set:
					text = "{} ({})".format(barcodeData, barcodeType)
					color = (255, 0 , 0)

					keys_found_set.add(chave)
					
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
		addLog("[ERROR] File not found in request.")
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


def save_data_gspread(df_dados):
    try:
        #Open the Worksheet in the Google Drive
        worksheet = google_sheet.save_data_gspread()
        #Convert DataFrame to list
        df_values = df_dados.values.tolist() 
        #Append values in the Spreadsheet
        worksheet.append_rows(values=df_values)
        
        return True
    except Exception as e:
        print('[ERROR]', e)
        
        return False

def decodeNF(chave, tryCount=1):
	global keys_found_set, df_coupons, nfce
	addLog("[INFO] Connecting to NFCe URL ... Key: {}".format(chave))
					
	url = f"https://www.sefaz.rs.gov.br/ASP/AAE_ROOT/NFE/SAT-WEB-NFE-COM_2.asp?chaveNFe={chave}&HML=false&NFFCBA06010"

	#Connect to the NFCe page URL and get the data
	page = requests.post(url)
		
	#Test if the request page was successfully
	if page.status_code == 200:
		addLog("[INFO] Decoding data ...")
		new_data = nfce.get_data(page, chave, columns_coupons)
		df_coupons = pd.concat([df_coupons, new_data], axis=0, ignore_index=True)
		
		#Save data in file
		addLog("[INFO] Saving file on disc ...")
		df_coupons.to_csv(path_csv_coupons, index=False)

		#Save data on Google Spreadsheet
		google_sheet.save_data_gspread(new_data)

	else:
		addLog("[ERROR] Problem with connecting to the page of Sefaz: {}".format(page.status_code))
		if( tryCount < 4):
			addLog("[INFO] Trying to connect again, try count {}".format(tryCount))
			decodeNF(chave, tryCount + 1)
		else:
			addLog("[ERROR] Could not connect to server SEFAZ, try in few minutes . . .")
			keys_found_set.remove(chave)
		
		
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
		global df_coupons
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