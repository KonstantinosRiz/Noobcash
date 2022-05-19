from copy import deepcopy
import time
import noobcash
from noobcash.api import transaction_api

def broadcast_mempool():
    while True:
        # * Copy node state for this iteration so that we dont crash if state is modified by another thread
        noobcash.current_node.master_state_lock.acquire()
                
        active_state = deepcopy(noobcash.current_node.active_blocks_log[noobcash.current_node.active_block.uuid]) if noobcash.current_node.active_block is not None else deepcopy(noobcash.current_node.current_state)
        
        # * Clean up mempool from transactions that are in current state
        for processed_transaction_id in list(noobcash.current_node.current_state.processed_transactions):
            if processed_transaction_id in noobcash.current_node.mempool:
                del noobcash.current_node.mempool[processed_transaction_id]
                
        mempool = deepcopy(noobcash.current_node.mempool)
        noobcash.current_node.master_state_lock.release()
        
        # * Broadcast transactions and add them to active block
        for transaction_id, transaction in mempool.items():
            if transaction_id not in active_state.processed_transactions:  
                noobcash.current_node.validate_and_add_transaction_to_block(transaction)
            
            transaction_api.broadcast_transaction(transaction=transaction)
            
        # * Sleep and then repeat
        time.sleep(10)