#!/usr/bin/env python3

import os
from threading import Thread
from time import sleep
from dotenv import load_dotenv
import requests

load_dotenv('../env/.env')

NODE_NUM = int(os.getenv('NODE_NUM'))

node_info = {}
for node_id in range(NODE_NUM):
    node_id = str(node_id)
    
    node_info[node_id] = {'ip': os.getenv(f'IP_ADDRESS_NODE_{node_id}'), 'port': os.getenv(f'PORT_NODE_{node_id}')}
    while True:
        try:
            print(f"http://{node_info[node_id]['ip']}:{node_info[node_id]['port']}/create_node")
            response = requests.post(f"http://{node_info[node_id]['ip']}:{node_info[node_id]['port']}/create_node", json={'ip':node_info[node_id]['ip'], 'port': node_info[node_id]['port'], 'bootstrap_port': node_info['0']['port'], 'bootstrap_ip':node_info['0']['ip']})
            break
        except Exception:
            pass
        
        sleep(1)
