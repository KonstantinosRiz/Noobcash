#!/usr/bin/env python3

import cmd
from http.client import ResponseNotReady
import requests

class Noobcash(cmd.Cmd):
    intro = '\nWelcome to the noobcash client. Type help or ? to list commands.\n'
    prompt = 'noobcash> '
    
    def preloop(self):
        self.ip = input('Enter the ip of your node (defaults to localhost): ')
        if self.ip == '':
            self.ip = '127.0.0.1'
        self.port = input('Enter the port of your node: ')
    
    def do_balance(self, arg):
        'Get the node balance'
        response = requests.get(f'http://{self.ip}:{self.port}/balance')
        print(f"Available Balance: {response.json()['balance']} NBC")
        print(f"Unconfirmed Spending: {response.json()['unconfirmed_spending']} NBC")
        
    def do_view(self, arg):
        'Get transactions in last blockchain block'
        response = requests.get(f'http://{self.ip}:{self.port}/view')
        transaction_list = response.json()['data']
        for transaction_dict in transaction_list:
            print("**********************************************************")
            print(f"Transaction id: {transaction_dict['transaction_id']}")
            print(f"Transaction sender address: {transaction_dict['sender_address']}")
            print(f"Transaction recipient address: {transaction_dict['recipient_address']}")
            print(f"Transaction amount: {transaction_dict['amount']}")
            print(f"Transaction signature: {transaction_dict['signature']}")
            
    def do_t(self, arg):
        't <recipient_address> <amount>. Create transaction with given recipient and amount.'
        try:
            recipient, amount = arg.split(' ')
            amount = float(amount)
        except Exception as e:
            print("Wrong input formatting: t <recipient_address> <amount>")
            return

        response = requests.post(f'http://{self.ip}:{self.port}/transaction/create', data={'recipient_id': recipient, 'amount': amount})
        
        print(response.text)
        
    def do_exit(self, arg):
        'Exit the noobcash client.'
        return True
        

if __name__ == '__main__':
    Noobcash().cmdloop()