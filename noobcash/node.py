# import block
import base64
from copy import deepcopy
from functools import partial
import logging
import threading
from dataclasses import dataclass
from time import time

import Crypto
import requests
from Crypto.Hash import SHA256

import noobcash
from noobcash.api import blockchain_api, block_api
from noobcash.block import Block
from noobcash.blockchain import Blockchain
from noobcash.exceptions import InsufficientFundsException, NegativeAmountException
from noobcash.transaction import Transaction
from noobcash.transaction_input import TransactionInput
from noobcash.transaction_output import TransactionOutput
from noobcash.wallet import Wallet
from noobcash.state import State

logger = logging.getLogger()

started_block_counting = False
started_trans_counting = False
class Node:
    def __init__(self):
        
        self.id = '0'
        self.blockchain: Blockchain = Blockchain()
        self.wallet = Wallet()
        
        # Here we store non changing information for every node, as its id, its address (ip:port) its public key 
        self.ring = { '0': { 'ip': '127.0.0.1', 'port': '5000' } }

        self.active_block = None
        self.mining_block = None
        
        # * This holds the state of all blocks in the blockchain
        self.shadow_log: dict[str, State] = {}
        
        # * This holds the state of all the blocks currently being processed
        # * This can be: 1. The block i am currently adding transactions to, 2. The block being mined
        self.active_blocks_log: dict[str, State] = {}
        
        self.current_state: State | None = None

        self.mining_lock = threading.Lock()
        self.master_state_lock = threading.Lock()
        self.mining_sem = threading.Semaphore(value=2)
        
        # * This contains all transactions we have created and are not in the blockchain
        self.mempool = {}

        # * Metric variables
        self.block_time = 0
        self.trans_time = 0
        self.trans_count = 0
        self.start_trans_time = 0
        self.start_block_time = 0
        self.started_block_counting = False
        self.started_trans_counting = False

    def create_initial_blockchain(self):
        '''
            This if the first function being run from the bootstrap that initiates the whole blockchain by creating the genesis block
        '''
        genesis_transaction_input = TransactionInput(TransactionOutput(self.wallet.public_key.decode(), 100*noobcash.NODE_NUM, base64.b64encode(SHA256.new(b'parent_id').digest()).decode('utf-8')))
        genesis_transaction = Transaction(Crypto.PublicKey.RSA.generate(2048).public_key().export_key().decode(), self.wallet.public_key.decode("utf-8"), 100*noobcash.NODE_NUM, [genesis_transaction_input])
        genesis_transaction_output = genesis_transaction.get_recipient_transaction_output()
                
        genesis_block = Block(base64.b64encode(SHA256.new(bytes(1)).digest()).decode('utf-8'))
        genesis_block.add_transaction(genesis_transaction)
        
        genesis_block.hash = base64.b64encode(genesis_block.compute_hash()).decode('utf-8')
        
        for transaction_input in genesis_transaction.transaction_inputs:
            self.wallet.STXOs.add(transaction_input.id)
        self.wallet.UTXOs = []
        self.wallet.add_transaction_output(genesis_transaction_output)
        
        self.id = '0'
        
        self.ring[self.id]['public_key'] = self.wallet.public_key.decode()
        
        self.blockchain = Blockchain()
        self.blockchain.add_block(genesis_block)
        
        initial_utxo_dict = {str(node_id): {} for node_id in range(noobcash.NODE_NUM)}
        initial_utxo_dict['0'] = { genesis_transaction_output.id: genesis_transaction_output}
        self.current_state = State(initial_utxo_dict, { genesis_transaction.transaction_id })
        self.shadow_log[genesis_block.hash] = deepcopy(self.current_state)

    #####################################**######################################
    ##########################* Transaction functions *##########################
    #####################################**######################################

    def validate_transaction(self, transaction: Transaction, state: State):  
        '''
            This checks the validity of a given transaction based on the state we give (which should be the active state of the block)
        ''' 
        # 1. make sure that transaction signature is valid
        # 2. check that the sender node has enough balance based on its UTXOs
        # * Check that transaction is not already in blockchain
        is_not_already_processed = transaction.transaction_id not in state.processed_transactions
        
        # * Check that transaction is valid
        has_valid_signature = transaction.verify_signature()
        
        sender_address = transaction.sender_address       
        sender_node_id = self.get_node_id_from_address(sender_address)
        
        has_invalid_transaction_inputs = False
        for transaction_input in transaction.transaction_inputs:
            is_unspent_transaction = transaction_input.id in state.utxos[sender_node_id]
            
            if is_unspent_transaction is False:
                has_invalid_transaction_inputs = True
                break
        
        is_valid_transaction = is_not_already_processed and has_valid_signature and not has_invalid_transaction_inputs
        
        return is_valid_transaction
    
    def process_transaction(self, transaction: Transaction, state: State):
        """Update state based on transaction

        Args:
            transaction (Transaction): The current transaction
            state (State): The state to be updated. WARNING: This must be a pointer to the state!!!
        """        
        sender_address = transaction.sender_address
        recipient_address = transaction.recipient_address
        
        sender_node_id = self.get_node_id_from_address(sender_address)
        recipient_node_id = self.get_node_id_from_address(recipient_address)
        
        sender_transaction_output = transaction.get_sender_transaction_output()
        recipient_transaction_output = transaction.get_recipient_transaction_output()

        # * Even while the sender uses all their UTXOS to create their transactions I may have some of their UTXOs that they haven't
        # * because I may have created a transaction with them as the recipient that they haven't yet received
        for transaction_input in transaction.transaction_inputs:
            if transaction_input.id in state.utxos[sender_node_id]:
                del state.utxos[sender_node_id][transaction_input.id]

        state.utxos[sender_node_id][sender_transaction_output.id] = sender_transaction_output
        state.utxos[recipient_node_id][recipient_transaction_output.id] = recipient_transaction_output
        
        state.processed_transactions.add(transaction.transaction_id)
    
    # * I should not be changing my UTXOs based on the active state because I know that everytime I create a transaction it is a valid transactions
    # * and I should not be spending those UTXOs again lest I invalidate the previous transaction
    def create_transaction_and_add_to_block(self, node_id, amount):
        '''
            This creates our transaction and adds it to the block if we validate it. Of course it is valid when created, but it is possible that is is invalid
            at the moment based on the active state, but it will certainly be valid at some state of the blockchain if we don't lose any transactions.
        '''
        
        # * We can only add new transactions to the block if there are not 2 blocks currently trying to be mined: otherwise wait
        self.mining_sem.acquire()
        # print(f'{self.id} acquiring master lock create_transaction_and_add_to_block')
        self.master_state_lock.acquire()
        # print(f'{self.id} acquired master lock create_transaction_and_add_to_block')
        
        # Create a transaction with someone giving them the requested amount
        self.update_current_block()
        
        receiver_public_key = self.ring[node_id]['public_key']
        active_state = self.active_blocks_log[self.active_block.uuid]
        
        public_key, private_key = self.wallet.get_key_pair()
        my_UTXOs = [utxo for utxo in self.wallet.UTXOs]
        
        transaction_inputs = [TransactionInput(UTXO) for UTXO in my_UTXOs]
        
        # Try creating it and handle the error of not having enough balance
        try:
            new_transaction = Transaction(public_key.decode(), receiver_public_key, amount=amount, transaction_inputs=transaction_inputs)
        except InsufficientFundsException as e:
            # print(f'{self.id} releasing master lock create_transaction_and_add_to_block')
            self.master_state_lock.release()
            self.mining_sem.release()
            raise e
        except NegativeAmountException as e:
            # print(f'{self.id} releasing master lock create_transaction_and_add_to_block')
            self.master_state_lock.release()
            self.mining_sem.release()
            raise e
        
        # Sign the transaction
        new_transaction.sign_transaction(private_key)
        
        # * Add the newly created transaction to the mempool
        self.mempool[new_transaction.transaction_id] = new_transaction
        
        # * Update wallet
        for utxo in my_UTXOs:
            self.wallet.STXOs.add(utxo.id)
        self.wallet.UTXOs = []
        self.wallet.add_transaction_output(new_transaction.get_sender_transaction_output())
        
        # * Only if valid based on active state, process it
        if self.validate_transaction(new_transaction, active_state):
            self.process_transaction(new_transaction, active_state)
            self.active_block.add_transaction(new_transaction)
            
            # * Calculating metrics
            if self.started_trans_counting:
                self.trans_count += 1
                self.trans_time += time() - self.start_trans_time
                logger.info(f'Current-Thoughput({self.trans_count}): {self.trans_count / self.trans_time}')
            else:
                self.started_trans_counting = True
            self.start_trans_time = time()
            # * Done calculating for this transaction
            
            # * If capacity reached, start mining
            if self.active_block.capacity == self.active_block.get_length():
                self.mine_current_block()
        
        # print(f'{self.id} releasing master lock create_transaction_and_add_to_block')
        self.master_state_lock.release()
        self.mining_sem.release()
        
        return new_transaction
    
    def validate_and_add_transaction_to_block(self, transaction: Transaction):
        '''
            This function runs when we receive a transaction from another node, then we check its validity and we add it to the current block if valid.
        '''
        self.mining_sem.acquire()
        # print(f'{self.id} acquiring master lock validate_and_add_transaction_to_block')
        self.master_state_lock.acquire()
        # print(f'{self.id} acquired master lock validate_and_add_transaction_to_block')
        
        # This creates a new block if one is not already active
        self.update_current_block()
        
        active_state = self.active_blocks_log[self.active_block.uuid]
        
        is_valid = self.validate_transaction(transaction, active_state)
        
        if is_valid:
            self.process_transaction(transaction, active_state)
            
            self.active_block.add_transaction(transaction)
            
            # * Calculating metrics
            if self.started_trans_counting:
                self.trans_count += 1
                self.trans_time += time() - self.start_trans_time
                logger.info(f'Current-Thoughput({self.trans_count}): {self.trans_count / self.trans_time}')
            else:
                self.started_trans_counting = True
            self.start_trans_time = time()
            # * Done calculating for this transaction
            
            if self.active_block.capacity == self.active_block.get_length():
                self.mine_current_block()
        
        # print(f'{self.id} releasing master lock validate_and_add_transaction_to_block')
        self.master_state_lock.release()
        self.mining_sem.release()
        
    #####################################**######################################
    #############################* Block functions *#############################
    #####################################**######################################
        
    def update_current_block(self):
        if self.active_block is not None:
            return
                
        if self.mining_block is not None:
            # * Use the mining block's timestamp as previous hash so that before we start mining if the previous hash equals the latest blockchain block's timestamp
            # * then we need toreplace our previous hash with its hash (found after it finished mining) else we must be yeeted
            new_block = Block(self.mining_block.uuid)
            mining_block_state = self.active_blocks_log[self.mining_block.uuid]
            self.active_blocks_log[new_block.uuid] = deepcopy(mining_block_state)
        else:
            new_block = Block(self.blockchain.last_hash)
            self.active_blocks_log[new_block.uuid] = deepcopy(self.current_state)
        
        self.active_block = new_block
        
    def validate_block(self, block: Block, current_state: State):
        '''
            This is run when we receive a mined block from another node.
            We validate the given block based on the given state (which should be the current state of the blockchain)
        '''      
        # print(f"{self.id}:[validate_block] start")
        block_state = deepcopy(current_state)
                
        has_invalid_transaction = False
        for transaction in block.list_of_transactions:
            if self.validate_transaction(transaction, block_state) is False:
                has_invalid_transaction = True
                break
            else:
                self.process_transaction(transaction, block_state)
            
        has_valid_hash = block.validate_hash()
        
        # print(f"{self.id}:[validate_block] has_valid_hash: {has_valid_hash}, has_invalid_transaction: {has_invalid_transaction}")
        
        if has_valid_hash and not has_invalid_transaction:
            return True, block_state
        else:
            return False, None
            
    def add_block_to_blockchain(self, block: Block):
        '''
            Add block that we received from another node to our blockchain after checking its validity. If it's not valid run a consensus to check we have the latest version
            of the blockchain.
        '''
        # print(f'{self.id} acquiring master lock add_block_to_blockchain')
        self.master_state_lock.acquire()
        # print(f'{self.id} acquired master lock add_block_to_blockchain')
        
        is_valid_block, block_state = self.validate_block(block, self.current_state)
        is_next_block = self.blockchain.last_hash == block.previous_hash
        
        if is_valid_block and is_next_block:
            # print(f'adding block')
            # * Update blockchain
            self.blockchain.add_block(block)
            self.shadow_log[block.hash] = deepcopy(block_state)
            self.current_state = deepcopy(block_state)
            
            # * Update my wallet UTXOs based on new current state
            for _, utxo in self.current_state.utxos[self.id].items():
                self.wallet.add_transaction_output(utxo)
            
            if self.mining_block is not None:
                self.mining_block.failed = True
                
            if self.active_block is not None:
                self.active_block.failed = True
                if self.active_block.uuid in self.active_blocks_log:
                    del self.active_blocks_log[self.active_block.uuid]
                self.active_block = None
            
            # * Calculating metrics
            if self.started_block_counting:
                self.block_time += time() - self.start_block_time
                logger.info(f'Current-Blocktime({len(self.blockchain.chain) - 2}): {self.block_time / ( len(self.blockchain.chain) - 2)}')
            else:
                self.started_block_counting = True
            self.start_block_time = time()
            # * Done calculating for this block

            # print(f'{self.id} releasing master lock add_block_to_blockchain')
            self.master_state_lock.release()
            # print(f'{self.id}: done adding block')
            return True
        else:
            # print(f'{self.id}: consensus')
            self.consensus()
            # print(f'{self.id}: run consensus')
            # print(f'{self.id} releasing master lock add_block_to_blockchain')
            self.master_state_lock.release()
            return False   
                 
    def yeet_block(self, block_to_be_yeeted: Block):
        '''
            This functions runs when consensus is run and the blockchain changes, so as to guarantee that we won't lose any transactions.
        '''
        for transaction in block_to_be_yeeted.list_of_transactions:
            sender_node_id = self.get_node_id_from_address(transaction.sender_address)
            if sender_node_id == self.id:
                self.mempool[transaction.transaction_id] = transaction
                
    #####################################**######################################
    ##########################* Blockchain functions *###########################
    #####################################**######################################
        
    def validate_blockchain(self, partial_chain: Blockchain, last_consensual_block_hash: str):
        '''
            This function runs during consensus when we receive blockchains from the other nodes to find the longest one.
            After having sent our own chain of hashes we receive the partial chain with the blocks we disagree with the other node and the hash of the last block we agree on.
        '''
        # print('i am in validate_blockchain whaaaaattttt')
        # * Set up incoming_blockchains shadow_log up to the point where we disagree
        blockchains_shadow_log = {}
        is_last_consensual_block_in_our_blockchain = False
        
        for block in self.blockchain.chain:
            blockchains_shadow_log[block.hash] = deepcopy(self.shadow_log[block.hash])
            
            if last_consensual_block_hash == block.hash:
                is_last_consensual_block_in_our_blockchain = True
                break
        
        # * Check that the other guy is not lying about last_consensual_block_hash
        if not is_last_consensual_block_in_our_blockchain:
            return False, None
        
        # * In case that we agree on all blocks in other node's blockchain just return
        if partial_chain.get_length() == 0:
            return True, blockchains_shadow_log
        
        # * If partial_chain has blocks, validate them and expand blockchain's shadow_log
        is_continuation_of_our_chain = partial_chain.chain[0].previous_hash == last_consensual_block_hash
            
        if not is_continuation_of_our_chain:
            return False, None
            
        current_state = deepcopy(blockchains_shadow_log[last_consensual_block_hash])
        previous_block_hash = last_consensual_block_hash
        for block in partial_chain.chain:
            is_block_valid, current_state = self.validate_block(block, current_state)
            is_chain = block.previous_hash == previous_block_hash
            previous_block_hash = block.hash
            
            if not (is_block_valid and is_chain):
                return False, None
            
            blockchains_shadow_log[block.hash] = deepcopy(current_state)
        
        return True, blockchains_shadow_log

    #####################################**######################################
    #####################* Consensus and helper functions *######################
    #####################################**######################################
    
    def consensus(self):
        '''
            !!! WARNING !!!!    consensus is only run when we are using function "add block to blockchain" which receives a block from another node and initializes actions to
                                check it and add it to the blockchain, which is always done with the master state locked.
            
            This function runs when we try to add a block to our blockchain and we fail to do so, due to failure of hashes. We a
        '''      
        chains = []
        for key in self.ring.keys():
            node_id = key
            node_ip = self.ring[key]['ip']
            node_port = self.ring[key]['port']
            
            if node_id != self.id:
                partial_chain, last_consensual_block_hash = blockchain_api.get_blockchain_from_node(node_ip, node_port)
                is_valid, blockchain_shadow_log = self.validate_blockchain(partial_chain, last_consensual_block_hash)
                if is_valid:
                    chain = Blockchain()
                    for block in self.blockchain.chain:
                        chain.add_block(block)
                        if block.hash == last_consensual_block_hash:
                            break
                    for block in partial_chain.chain:
                        chain.add_block(block)
                    
                    chains.append({ 'chain': chain, 'shadow_log': blockchain_shadow_log, 'last_consensual_block_hash': last_consensual_block_hash })
            
        chains.append({ 'chain': self.blockchain, 'shadow_log': self.shadow_log, 'last_consensual_block_hash': self.blockchain.last_hash })       
        winner_chain = self.get_longest_chain(chains)
        last_consensual_block_hash = winner_chain['last_consensual_block_hash']

        if self.blockchain.last_hash == winner_chain['chain'].last_hash:
            return
        
        # * First we backup the blockchain to be able to re-do the transactions of the yeeted blocks. Then we update the blockchain and the other variables so that the hash
        # * of the new block to be created will be the proper one. Afterwards, we yeet both the block we were creating and also the blocks we removed from our blockchain.
        blockchain_backup = deepcopy(self.blockchain)
        
        # * First update blockchain to the winning one
        self.blockchain: Blockchain = winner_chain['chain'] 
        self.shadow_log: dict[str, State] = winner_chain['shadow_log']
        self.current_state = self.shadow_log[self.blockchain.last_hash]
        for _, utxo in self.current_state.utxos[self.id].items():
            self.wallet.add_transaction_output(utxo)
            
        if self.mining_block is not None:
            self.mining_block.failed = True
            
        if self.active_block is not None:
            # * We update its 'failed' status in case there is another pointer to this block waiting to be mined at the lock (current_block in threaded_mining)
            self.active_block.failed = True
            if self.active_block.uuid in self.active_blocks_log:
                del self.active_blocks_log[self.active_block.uuid]
            self.active_block = None
        
        # * Before replacing blockchain add transactions that I created which will be removed from the blockchain to the mempool
        should_be_yeeted = False
        for block in blockchain_backup.chain:
            if should_be_yeeted:
                self.yeet_block(block)
            else:
                if block.hash == last_consensual_block_hash:
                    should_be_yeeted = True

    def get_longest_chain(self, chains):
        '''
            Just returns the first longest chain from a list of chains.
        '''
        biggest = -1
        winner = None
        
        for chain in chains:
            chain_length = chain['chain'].get_length()
            if chain_length >= biggest:
                biggest = chain_length
                winner = chain
                
        return winner
    
    def get_partial_chain(self, hash_list):
        '''
            After receiving the hash_list of the node requesting our blockchain, we return the chain from the point we disagree on and also the hash of the last block we agree on.
        '''
        last_consensual_hash = None
        partial_chain = Blockchain()
        
        for i, block in enumerate(self.blockchain.chain):
            if last_consensual_hash is None:
                try:
                    if block.hash != hash_list[i]:
                        last_consensual_hash = block.previous_hash
                        partial_chain.add_block(block) 
                except:
                    last_consensual_hash = block.previous_hash
                    partial_chain.add_block(block)
            else:
                partial_chain.add_block(block)

        last_consensual_hash = last_consensual_hash if last_consensual_hash is not None else self.blockchain.last_hash

        return partial_chain, last_consensual_hash
    
    #####################################**######################################
    ############################* Mining functions *#############################
    #####################################**######################################
    
    def mine_current_block(self):
        # * This holds the states of our currently mining blocks
        mining_thread = threading.Thread(target=self.threaded_mining, args=(self.active_block, self.mining_end))
        mining_thread.start()
        
        self.active_block = None
    
    def threaded_mining(self, current_block: Block, callback_function):
        '''
            This function is run on another thread.
        '''
        self.mining_sem.acquire()
        self.mining_lock.acquire()
        # print(f'{self.id} acquiring master lock threaded_mining')
        self.master_state_lock.acquire()
        # print(f'{self.id} acquired master lock threaded_mining')
        
        self.mining_block = current_block
        
        if self.mining_block.previous_hash == self.blockchain.chain[-1].uuid:
            # * If I was created with the assumption that a previous mining block would have entered the blockchain by now then I should check that it actually did
            self.mining_block.previous_hash = self.blockchain.last_hash
        
        if self.mining_block.previous_hash != self.blockchain.last_hash or current_block.failed:
            # * If I was created to further the current blockchain, I should check that the blockchain hasn't changed since then
            self.mining_block.failed = True
            del self.active_blocks_log[self.mining_block.uuid]
            self.mining_block = None
            
            if self.active_block is not None:
                self.active_block.failed = True
                if self.active_block.uuid in self.active_blocks_log:
                    del self.active_blocks_log[self.active_block.uuid]
                self.active_block = None
                
            # print(f'{self.id} releasing master lock threaded_mining')
            self.master_state_lock.release()
            self.mining_lock.release()
            self.mining_sem.release()
            return
            
        # print(f'{self.id} releasing master lock threaded_mining')
        self.master_state_lock.release()
            
        # * Only if I was created to further the current blockchain and it still hasn't changed since then, I should truly start the mining
        self.mining_block.mine()
        
        callback_function()
        
    def mining_end(self):
        '''
            This is run when a block finishes mining and does the update if successful or cleans up if it fails.
        '''
        # print(f'{self.id} acquiring master lock mining_end')
        self.master_state_lock.acquire()
        # print(f'{self.id} acquired master lock mining_end')
        
        # print(f'{self.id}: mining end start')
        # Check that mining was successful
        has_valid_hash = self.mining_block.validate_hash()
        is_next_in_chain = self.blockchain.last_hash == self.mining_block.previous_hash
        
        if has_valid_hash and is_next_in_chain and not self.mining_block.failed:
            # * Update blockchain
            self.blockchain.add_block(self.mining_block)
            self.shadow_log[self.mining_block.hash] = deepcopy(self.active_blocks_log[self.mining_block.uuid])
            self.current_state = deepcopy(self.active_blocks_log[self.mining_block.uuid])
            
            # * Use the current state to update my wallet's UTXOs
            for _, utxo in self.current_state.utxos[self.id].items():
                self.wallet.add_transaction_output(utxo)
            # print(f'{self.id}: added mined block broadcasting')
            # Broadcast block
            block_api.broadcast_block(self.mining_block, self.ring)

            # * Calculating metrics
            if self.started_block_counting:
                self.block_time += time() - self.start_block_time
                logger.info(f'Current-Blocktime({len(self.blockchain.chain) - 2}): {self.block_time / ( len(self.blockchain.chain) - 2)}')
            else:
                self.started_block_counting = True
            self.start_block_time = time()
            # * Done calculating for this block
        else:
            # print(f'{self.id}: mined block yeeted')
            if self.active_block is not None:
                self.active_block.failed = True
                if self.active_block.uuid in self.active_blocks_log:
                    del self.active_blocks_log[self.active_block.uuid]
                self.active_block = None
             
        # * Cleanup in any case 
        del self.active_blocks_log[self.mining_block.uuid]
        self.mining_block = None

        # print(f'{self.id} releasing master lock mining_end')       
        self.master_state_lock.release()
        self.mining_lock.release()
        self.mining_sem.release()
        
        # print(f'{self.id}: exited mining')
    
    def get_node_id_from_address(self, address):
        '''
            Utility function.
        '''
        node_id = None
        for key, node_info in self.ring.items():
            if node_info['public_key'] == address:
                node_id = key
                break
        return node_id
