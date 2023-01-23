import base64
import json
from algosdk.future import transaction
from algosdk.future.transaction import AssetConfigTxn, AssetTransferTxn, AssetFreezeTxn, wait_for_confirmation, PaymentTxn
from algosdk import account, mnemonic
from algosdk.v2client import algod
from pyteal import compileTeal, Mode
from smart_contract import approval_program, clear_state_program


# user declared algod connection parameters. Node must have EnableDeveloperAPI set to true in its config
algod_address = "https://testnet-idx.algonode.cloud"

# helper function to compile program source
def compile_program(client, source_code):
    compile_response = client.compile(source_code)
    return base64.b64decode(compile_response["result"])


# helper function that converts a mnemonic passphrase into a private signing key
def get_private_key_from_mnemonic(mn):
    private_key = mnemonic.to_private_key(mn)
    return private_key

def fund_new_acct(client, addr, amt, funding_mnemonic):
    sender_private_key=mnemonic.to_private_key(funding_mnemonic)
    sender=account.address_from_private_key(sender_private_key)

    unsigned_txn = transaction.PaymentTxn(sender, client.suggested_params(), addr,amt, None)
    signed_txn = unsigned_txn.sign(sender_private_key)

    #submit transaction
    txid = client.send_transaction(signed_txn)
    print("Successfully sent transaction with txID: {}".format(txid))

    # wait for confirmation 
    try:
        confirmed_txn = wait_for_confirmation(client,txid)  
    except Exception as err:
        print(err)
        return


def wait_for_round(client, round):
    last_round = client.status().get("last-round")
    print(f"Waiting for round {round}")
    while last_round < round:
        last_round += 1
        client.status_after_block(last_round)
        print(f"Round {last_round}")


# create new application
def create_app(
    client,
    private_key,
    approval_program,
    clear_program,
    global_schema,
    local_schema,
    app_args,
):
    # define sender as creator
    sender = account.address_from_private_key(private_key)

    # declare on_complete as NoOp
    on_complete = transaction.OnComplete.NoOpOC.real

    # get node suggested parameters
    params = client.suggested_params()
    # comment out the next two (2) lines to use suggested fees
    params.flat_fee = True
    params.fee = 1000

    # create unsigned transaction
    txn = transaction.ApplicationCreateTxn(
        sender,
        params,
        on_complete,
        approval_program,
        clear_program,
        global_schema,
        local_schema,
        app_args,
    )

    # sign transaction
    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()

    # send transaction
    client.send_transactions([signed_txn])

    # await confirmation
    wait_for_confirmation(client, tx_id)

    # display results
    transaction_response = client.pending_transaction_info(tx_id)
    app_id = transaction_response["application-index"]
    print("Created new app-id:", app_id)

    return app_id


# opt-in to application
def opt_in_app(client, private_key, index):
    # declare sender
    sender = account.address_from_private_key(private_key)
    print("OptIn from account: ", sender)

    # get node suggested parameters
    params = client.suggested_params()
    # comment out the next two (2) lines to use suggested fees
    params.flat_fee = True
    params.fee = 1000

    # create unsigned transaction
    txn = transaction.ApplicationOptInTxn(sender, params, index)

    # sign transaction
    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()

    # send transaction
    client.send_transactions([signed_txn])

    # await confirmation
    wait_for_confirmation(client, tx_id)

    # display results
    transaction_response = client.pending_transaction_info(tx_id)
    print("OptIn to app-id:", transaction_response["txn"]["txn"]["apid"])


# call application
def call_app(client, private_key, index, app_args, accounts, foreign_assets):
    # declare sender
    sender = account.address_from_private_key(private_key)
    print("Call from account:", sender)

    # get node suggested parameters
    params = client.suggested_params()
    # comment out the next two (2) lines to use suggested fees
    params.flat_fee = True
    params.fee = 1000

    # create unsigned transaction
    txn = transaction.ApplicationNoOpTxn(sender, params, index, app_args, accounts=accounts, foreign_assets=foreign_assets)

    # sign transaction
    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()

    # send transaction
    client.send_transactions([signed_txn])

    # await confirmation
    wait_for_confirmation(client, tx_id)


def format_state(state):
    formatted = {}
    for item in state:
        key = item["key"]
        value = item["value"]
        formatted_key = base64.b64decode(key).decode("utf-8")
        if value["type"] == 1:
            # byte string
            if formatted_key == "voted":
                formatted_value = base64.b64decode(value["bytes"]).decode("utf-8")
            else:
                formatted_value = value["bytes"]
            formatted[formatted_key] = formatted_value
        else:
            # integer
            formatted[formatted_key] = value["uint"]
    return formatted


# read user local state
def read_local_state(client, addr, app_id):
    results = client.account_info(addr)
    for local_state in results["apps-local-state"]:
        if local_state["id"] == app_id:
            if "key-value" not in local_state:
                return {}
            return format_state(local_state["key-value"])
    return {}


# read app global state
def read_global_state(client, addr, app_id):
    results = client.account_info(addr)
    apps_created = results["created-apps"]
    for app in apps_created:
        if app["id"] == app_id:
            return format_state(app["params"]["global-state"])
    return {}


# delete application
def delete_app(client, private_key, index):
    # declare sender
    sender = account.address_from_private_key(private_key)

    # get node suggested parameters
    params = client.suggested_params()
    # comment out the next two (2) lines to use suggested fees
    params.flat_fee = True
    params.fee = 1000

    # create unsigned transaction
    txn = transaction.ApplicationDeleteTxn(sender, params, index)

    # sign transaction
    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()

    # send transaction
    client.send_transactions([signed_txn])

    # await confirmation
    wait_for_confirmation(client, tx_id)

    # display results
    transaction_response = client.pending_transaction_info(tx_id)
    print("Deleted app-id:", transaction_response["txn"]["txn"]["apid"])


# close out from application
def close_out_app(client, private_key, index):
    # declare sender
    sender = account.address_from_private_key(private_key)

    # get node suggested parameters
    params = client.suggested_params()
    # comment out the next two (2) lines to use suggested fees
    params.flat_fee = True
    params.fee = 1000

    # create unsigned transaction
    txn = transaction.ApplicationCloseOutTxn(sender, params, index)

    # sign transaction
    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()

    # send transaction
    client.send_transactions([signed_txn])

    # await confirmation
    wait_for_confirmation(client, tx_id)

    # display results
    transaction_response = client.pending_transaction_info(tx_id)
    print("Closed out from app-id: ", transaction_response["txn"]["txn"]["apid"])


# clear application
def clear_app(client, private_key, index):
    # declare sender
    sender = account.address_from_private_key(private_key)

    # get node suggested parameters
    params = client.suggested_params()
    # comment out the next two (2) lines to use suggested fees
    params.flat_fee = True
    params.fee = 1000

    # create unsigned transaction
    txn = transaction.ApplicationClearStateTxn(sender, params, index)

    # sign transaction
    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()

    # send transaction
    client.send_transactions([signed_txn])

    # await confirmation
    wait_for_confirmation(client, tx_id)

    # display results
    transaction_response = client.pending_transaction_info(tx_id)
    print("Cleared app-id:", transaction_response["txn"]["txn"]["apid"])


# convert 64 bit integer i to byte string
def intToBytes(i):
    return i.to_bytes(8, "big")

#   Utility function used to print created asset for account and assetid
def print_created_asset(algodclient, account, assetid):    
    account_info = algodclient.account_info(account)
    idx = 0;
    for my_account_info in account_info['created-assets']:
        scrutinized_asset = account_info['created-assets'][idx]
        idx = idx + 1       
        if (scrutinized_asset['index'] == assetid):
            print("Asset ID: {}".format(scrutinized_asset['index']))
            print(json.dumps(my_account_info['params'], indent=4))
            break

#   Utility function used to print asset holding for account and assetid
def print_asset_holding(algodclient, account, assetid):
    account_info = algodclient.account_info(account)
    idx = 0
    for my_account_info in account_info['assets']:
        scrutinized_asset = account_info['assets'][idx]
        idx = idx + 1        
        if (scrutinized_asset['asset-id'] == assetid):
            print("Asset ID: {}".format(scrutinized_asset['asset-id']))
            print(json.dumps(scrutinized_asset, indent=4))
            break

# CREATE ASSET
def Create_asset(algodclient,private_key):
    # Get network params for transactions before every transaction.
    params = algodclient.suggested_params()
    main_address = account.address_from_private_key(private_key)
    # Asset Creation transaction
    txn = AssetConfigTxn(
        sender=main_address,
        sp=params,
        total=100000,
        default_frozen=False,
        unit_name="ENB",
        asset_name="ENB",
        manager=main_address,
        reserve=main_address,
        freeze=main_address,
        clawback=main_address,
        url="ipfs://enb", 
        decimals=0)

    
    # Sign with secret key of creator
    stxn = txn.sign(private_key)
    print("\n CREATE ASSET")
    try:
        txid = algodclient.send_transaction(stxn)
        print("Signed transaction with txID: {}".format(txid))
        confirmed_txn = wait_for_confirmation(algodclient, txid, 4)  
        print("TXID: ", txid)
        print("Result confirmed in round: {}".format(confirmed_txn['confirmed-round']))   
    except Exception as err:
        print(err)
    
    
    try:
    # Get the new asset's information from the creator account
        ptx = algodclient.pending_transaction_info(txid)
        asset_id = ptx["asset-index"]
        print_created_asset(algodclient, main_address, asset_id)
        print_asset_holding(algodclient, main_address, asset_id)
        return asset_id
    except Exception as e:
        print(e)

# OPT-IN
def Opt_in(algodclient,reciever_private_key,asset_id):
    params = algodclient.suggested_params()
    reciever_address = account.address_from_private_key(reciever_private_key)
    account_info = algodclient.account_info(reciever_address)
    holding = None
    idx = 0
    for my_account_info in account_info['assets']:
        scrutinized_asset = account_info['assets'][idx]
        idx = idx + 1    
        if (scrutinized_asset['asset-id'] == asset_id):
            holding = True
            break
    if not holding:
        # Use the AssetTransferTxn class to transfer assets and opt-in
        txn = AssetTransferTxn(
            sender=reciever_address,
            sp=params,
            receiver=reciever_address,
            amt=0,
            index=asset_id)

        stxn = txn.sign(reciever_private_key)
        print("\n OPT-IN")
        try:
            txid = algodclient.send_transaction(stxn)
            print("Signed transaction with txID: {}".format(txid))
            confirmed_txn = wait_for_confirmation(algodclient, txid, 4) 
            print("TXID: ", txid)
            print("Result confirmed in round: {}".format(confirmed_txn['confirmed-round']))    
        except Exception as err:
            print(err)
        
        print_asset_holding(algodclient, reciever_address, asset_id)
    
# TRANSFER ASSET
def Transfer_asset(algodclient,private_key,reciever_address,asset_id):
    params = algodclient.suggested_params()
    main_address = account.address_from_private_key(private_key)
    txn = AssetTransferTxn(
        sender=main_address,
        sp=params,
        receiver=reciever_address,
        amt=2000,
        index=asset_id)
    stxn = txn.sign(private_key)
    print("\n TRANSFER ASSET")
    try:
        txid = algodclient.send_transaction(stxn)
        print("Signed transaction with txID: {}".format(txid))
        confirmed_txn = wait_for_confirmation(algodclient, txid, 4) 
        print("TXID: ", txid)
        print("Result confirmed in round: {}".format(confirmed_txn['confirmed-round']))
    except Exception as err:
        print(err)
    # The balance should now be 10.
    print_asset_holding(algodclient, reciever_address, asset_id)