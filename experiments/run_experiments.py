#!/usr/bin/env python3

import os
from threading import Thread
from time import sleep
from dotenv import load_dotenv
import requests

load_dotenv('../env/.env')

NODE_NUM = int(os.getenv('NODE_NUM'))

def run_test(node_id, ip, port, transactions):
    if NODE_NUM <= 5:
        path = f'transactions_5_nodes/{transactions}'
    else:
        path = f'transactions_10_nodes/{transactions}'
    with open(path, 'r') as transactions_fh:
        request_url = f"http://{ip}:{port}/transaction/create"
        print(f'[{ip}, {port}, {transactions}] {request_url}')
        
        for transaction in transactions_fh:
            trans_info = transaction.split(' ')
            node_id = trans_info[0][2:]
            amount = trans_info[-1]
            print(f'[{ip}, {port}, {transactions}] {request_url} with data {node_id}, {amount}')
            r = requests.post(request_url, data={'recipient_id': node_id, 'amount': amount})

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
        
for node_id, info in node_info.items():
    t = Thread(target=run_test, args=[node_id, info['ip'], info['port'], f'transactions{node_id}.txt'])
    t.start()