import requests
url = "https://www.cmu-hch.com/cgi-bin/hc/reg64x.cgi?CliRoom=118&TimeCode=3"
r = requests.get(url)
r.encoding = 'big5'
print(r.text)
