import os
import sys
sys.path.insert(0, '/workspace')

from dotenv import load_dotenv
load_dotenv('.env.local')

# Check token expiry
import jwt
token = os.getenv('UPSTOX_ACCESS_TOKEN')
try:
    decoded = jwt.decode(token, options={"verify_signature": False})
    print(f"Token Subject: {decoded.get('sub')}")
    print(f"Token Expiry (exp): {decoded.get('exp')}")
    from datetime import datetime
    exp_date = datetime.fromtimestamp(decoded.get('exp'))
    print(f"Token Expired? {datetime.now() > exp_date}")
    print(f"Current Time: {datetime.now()}")
    print(f"Expiry Time: {exp_date}")
except Exception as e:
    print(f"Error decoding token: {e}")
