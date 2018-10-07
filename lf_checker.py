from bs4 import BeautifulSoup as bsoup
from urllib.request import Request, urlopen
from datetime import datetime
import smtplib
import time
import urllib
import pdfminer.settings
import os
import pdfminer.high_level
import pdfminer.layout
import sys
import pyrebase
import traceback

''' ' ' ' ' ' ' ' '
' Configurations  '
' ' ' ' ' ' ' ' '''
#PDFMiner Settings
pdfminer.settings.STRICT = False

#Email Settings
url = "https://ucpd.berkeley.edu/services/lost-and-found"
url_request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

#Command line parser
if len(sys.argv) < 4:
	gmail_user = input("Bot Email: ")
	gmail_pwd  = input("Bot Password: ")
	user_email = input("Recipient email: ")
else:
	gmail_user = sys.argv[1]
	gmail_pwd  = sys.argv[2]
	user_email = sys.argv[3]
FROM = "Lost and Found Bot"

#Firebase Config
config = {\
	"apiKey": "AIzaSyB-V1qWhNViHSnL7nyrK2WVyH2wmWF8338",\
	"authDomain": "berkeley-lost-and-found.firebaseapp.com",\
	"databaseURL": "https://berkeley-lost-and-found.firebaseio.com",\
	"storageBucket": "berkeley-lost-and-found.appspot.com"\
	}

firebase = pyrebase.initialize_app(config)
user = firebase.auth().sign_in_with_email_and_password(gmail_user, gmail_pwd)
db = firebase.database()

''' ' ' ' ' ' ' '
' Email Service '
' ' ' ' ' ' ' '''
def send_mail(recipients, link, new_items):
	if new_items:
		try:
			time = str(datetime.now())[0:19]
			subject = "Berkeley Lost and Found Update (%s)" % (time)
			body = "An update has been made to the UCPD lost and found pdf:\n%s\n" % (link)
			message = """From: %s\nTo: %s\nSubject: %s\n\n%s""" % (FROM, ", ".join(recipients), subject, body)
			message += "The following items have been added:\n\n"
			if new_items: 
				for ni in new_items: message += ni + "\n\n"
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

		
''' ' ' ' ' ' ' ' ' ' ' ' ' '
' PDF Retrieval and Parsing '
' ' ' ' ' ' ' ' ' ' ' ' ' '''
def get_pdf_link():
	try:
		html = urlopen(url_request).read()
		soup = bsoup(html, "html.parser")
		soup.prettify()
		target_div = soup.findAll("div", class_ = "field-item even")[0].findAll("p")[7]
		return target_div.a.get("href")
	except:
		traceback.print_exc()
		print("An error occurred while attempting to receive the pdf url.")
		return ""

def parse_pdf(pdf_link, storage_path = "pdfparse.tmp"):
	urllib.request.urlretrieve(pdf_link, storage_path)
	parsed = parse_text(extract_text(storage_path))
	os.remove(storage_path)
	return parsed

def extract_text(fname, outfile = "pdfextract.tmp"):
	laparams = pdfminer.layout.LAParams()
	for param in ("all_texts", "detect_vertical", "word_margin", "char_margin", "line_margin", "boxes_flow"):
		paramv = locals().get(param, None)
		if paramv is not None:
			setattr(laparams, param, paramv)
	with open(outfile, "wt", encoding = "utf-8") as outfp, open(fname, "rb") as infp:
		pdfminer.high_level.extract_text_to_fp(infp, **locals())
	with open(outfile, "rt") as infp:
		text = infp.read()
	os.remove(outfile)
	return text

def parse_text(text):
	lines = text.splitlines()
	items = []
	for i in range(len(lines)):
		curr_line = lines[i]
		if "Packaging/Quantity/Item Type:" in curr_line:
			item_type = curr_line[curr_line.index("-", curr_line.index("Qty:")) + 2:]
			description = "No description."
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
			while lines[j] and "Sub Total:" not in lines[j] and len(additional_info) < 3:
				additional_info.append(lines[j])
				j += 1
			items.append({"type": item_type, "desc": description, 
			"custody": custody, "info": additional_info})
	return items

def count_types(items):
	counts = {}
	for item in items:
		type = sanitize(item["type"])
		if type in counts:
			counts[type] += 1
		else:
			counts[type] = 1
	return counts

def sanitize(string):
	return string.replace('.', '')
	
''' ' ' ' ' ' '
' Comparisons '
' ' ' ' ' ' '''
def compare(curr, old):
	curr_descs = get_descriptions(curr)
	old_descs = get_descriptions(old)
	added = curr_descs - old_descs
	retrieved = old_descs - curr_descs
	return added, retrieved
	
def get_descriptions(items):
	if items:
		return set([item["desc"] for item in items if item])
	return ()

def update_items(pdf_link, items):
	update_time = datetime.now().strftime("%B %d, %Y at %I:%M %p")
	history_time = datetime.now().strftime("%m%d%Y")
	meta_data = {"time": update_time, "pdf": pdf_link}
	history_data = {history_time: count_types(items)}
	print(history_data)
	data = {"items": items, "meta": meta_data}
	db.child("items").remove(get_token())
	db.update(data, get_token())
	db.child("history").update(history_data, get_token())
	
def query(data_path):
	return db.child(data_path).get(get_token()).val()

def get_token():
	return firebase.auth().refresh(user['refreshToken'])["idToken"]

''' ' ' '
' Main  '
' ' ' '''
if __name__ == "__main__":
	while True:
		current_link = get_pdf_link()
		if current_link == query("meta/pdf") or not current_link:
			print("No updates have been detected.")
			update_time = datetime.now().strftime("%B %d, %Y at %I:%M %p")
			db.child("meta").update({"time": update_time}, get_token())
			print(str(datetime.now())[0:19])
			time.sleep(300)
		else:
			current_items = parse_pdf(current_link)
			old_items = query("items")
			update_items(current_link, current_items)
			lost, found = compare(current_items, old_items)
			print("===== ADDED =====")
			for l in lost: print(l + "\n")
			print("=== RETRIEVED ===")
			for f in found: print(f + "\n")
			send_mail([user_email], current_link, lost)
