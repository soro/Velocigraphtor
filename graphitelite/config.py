import json

f = open('../config/app.json')
lines = ''.join(f.readlines())
config = json.loads(lines)
