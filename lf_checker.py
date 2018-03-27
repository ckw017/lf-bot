from bs4 import BeautifulSoup as bsoup
from shutil import copyfile
from urllib.request import Request, urlopen
import smtplib
import datetime
import time
import urllib
import pdfminer.settings
import os
import pdfminer.high_level
import pdfminer.layout
import pickle
import sys
import json
import pyrebase

#PDFMiner Settings
pdfminer.settings.STRICT = False
url = 'https://ucpd.berkeley.edu/services/lost-and-found'
url_request = Request(url, headers={'User-Agent': 'Mozilla/5.0'})

#Command line parser
if len(sys.argv) < 4:
	gmail_user = input("Bot Email: ")
	gmail_pwd  = input("Bot Pass: ")
	user_email = input("Your email: ")
else:
	gmail_user = sys.argv[1]
	gmail_pwd  = sys.argv[2]
	user_email = sys.argv[3]
FROM = "Lost and Found Bot"

#Firebase Config
config = { 
	"apiKey": "AIzaSyAEvAGjNJR_wGMoHYAxiFaAHmSGdDwiiAs", \
	"authDomain": "fir-login-test-8ba99.firebaseapp.com", \
	"databaseURL": "https://fir-login-test-8ba99.firebaseio.com", \
	"storageBucket": "fir-login-test-8ba99.appspot.com"
	}
firebase = pyrebase.initialize_app(config)
user = firebase.auth().sign_in_with_email_and_password(gmail_user, gmail_pwd)
db = firebase.database()

resources_path = os.path.join(os.path.dirname(__file__), 'resources/')
storage_path = resources_path + 'curr_lf.pdf'
txt_storage_path = resources_path + 'curr_lf.txt'
txt_storage_path_old = resources_path + '/old_lf.txt'
history_path = os.path.join(os.path.dirname(__file__), 'resources/history/')
old_link = pickle.load(open(resources_path + 'old_link.p', 'rb'))

def extract_text(fname, outfile):
	laparams = pdfminer.layout.LAParams()
	for param in ("all_texts", "detect_vertical", "word_margin", "char_margin", "line_margin", "boxes_flow"):
		paramv = locals().get(param, None)
		if paramv is not None:
			setattr(laparams, param, paramv)
	outfp = open(outfile, "wt", encoding = 'utf-8')
	pdfminer.high_level.extract_text_to_fp(open(fname, "rb"), **locals())
	outfp.close()
	return outfp

def get_pdf_link():
	try:
		html = urlopen(url_request).read()
		soup = bsoup(html, 'html.parser')
		soup.prettify()
		targetDiv = soup.findAll("div", class_ = "field-item even")[7].findAll("p")[7]
		return targetDiv.a.get("href")
	except:
		print("An error occurred while attempting to receive the pdf url.")
		return current_link

def send_mail(recipients, link, new_items):
	if new_items:
		try:
			subject = "Berkeley Lost and Found Update (" + str(datetime.datetime.now())[0:19] + ")"
			body = "An update has been made to the UCPD lost and found pdf:\n" + link + '\n'
			message = """From: %s\nTo: %s\nSubject: %s\n\n%s""" % (FROM, ", ".join(recipients), subject, body)
			message += 'The following items have been added:\n'
			if new_items: 
				for ni in new_items: message += ni + '\n\n'
			server = smtplib.SMTP("smtp.gmail.com", 587)
			server.ehlo()
			server.starttls()
			server.login(gmail_user, gmail_pwd)
			server.sendmail(FROM, recipients, message)
			server.close()
			print("Successfully sent mail")
		except:
			print ("Failed to send mail.")
	else:
		print("No new items, email not sent.")

def parse_raw(raw_info):
	lines = raw_info.splitlines()
	parsed_info = []
	for i in range(len(lines)):
		curr_line = lines[i]
		if "Packaging/Quantity/Item Type:" in curr_line:
			item_type = curr_line[curr_line.index("-", curr_line.index("Qty:")) + 2:]
			description = 'No description.'
			j = i + 1
			if "Detail Description: " in lines[j]:
				description = lines[j].replace("Detail Description: ", "")
				j += 1
			while "Current Custody: " not in lines[j]:
				description += lines[j]
				j += 1
			custody = lines[j].replace("Current Custody: ", "").replace("Item Submitted Into Property - ", "")
			j += 1
			additional_info = []
			ad = 0
			while lines[j] and 'Sub Total:' not in lines[j] and ad < 3:
				additional_info += [lines[j]]
				j += 1
				ad += 1
			parsed_info.append({"type": item_type, "desc": description, 
			"custody": custody, "info": additional_info})
	return parsed_info

def compare(str1, str2):
	'''Returns tuple containing (added items, removed items) between two lost and found instances'''
	parsed1 = [item["desc"] for item in parse_raw(str1)]
	parsed2 = [item["desc"] for item in parse_raw(str2)]
	return list(set(parsed2) - set(parsed1)), list(set(parsed1) - set(parsed2))

def read(path):
	f = open(path, 'r') 
	s = f.read()
	f.close
	return s

def write_json(pdf_link, parsed_info):
	meta_data = {"time": getTimeString(), "pdf": pdf_link}
	data = {"items": parsed_info, "meta": meta_data}
	with open('result.json', 'w') as fp:
		json.dump(data, fp, indent = 4)
	db.remove(user["idToken"])
	db.update(data, user["idToken"])
	
def getTimeString():
	return datetime.datetime.now().strftime("%B %d, %Y at %I:%M:%S %p")
	
if __name__ == '__main__':
	while True:
		current_link = get_pdf_link()
		if current_link == old_link:
			print("No updates have been detected.")
			db.child("meta").update({"time": getTimeString()}, user["idToken"])
			print(str(datetime.datetime.now())[0:19])
			time.sleep(300)
		else:
			urllib.request.urlretrieve(current_link, storage_path)
			urllib.request.urlretrieve(current_link, history_path + current_link.replace('https://ucpd.berkeley.edu/sites/default/files/', ''))
			extract_text(storage_path, outfile = txt_storage_path)
			lost, found = compare(read(txt_storage_path_old), read(txt_storage_path))
			write_json(current_link, parse_raw(read(txt_storage_path)))
			print('===== ADDED =====')
			for l in lost: print(l + '\n')
			print('=== RETRIEVED ===')
			for f in found: print(f + '\n')
			send_mail([user_email], current_link, lost)
			copyfile(txt_storage_path, txt_storage_path_old)
			old_link = current_link
			pickle.dump(current_link, open(resources_path + 'old_link.p', 'wb'))