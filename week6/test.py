from helper import *
from algosdk.future import transaction
from algosdk import account, mnemonic
from algosdk.v2client import algod, indexer
from dotenv import load_dotenv
import os
import unittest

load_dotenv('../.env')
algod_address = "https://testnet-api.algonode.cloud"
indexer_address = "https://testnet-idx.algonode.cloud"
# user declared account mnemonics
funding_acct = os.environ.get('funding_acct')
funding_acct_mnemonic = os.environ.get('funding_acct_mnemonic')

unittest.TestLoader.sortTestMethodsUsing = None

class TestContract(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.algod_client = algod.AlgodClient("", algod_address)
        cls.algod_indexer = indexer.IndexerClient("", indexer_address)
        cls.funding_acct = funding_acct
        cls.funding_acct_mnemonic = funding_acct_mnemonic
        cls.new_acct_priv_key, cls.new_acct_addr = account.generate_account()
        cls.user_acct_priv_key, cls.user_acct_addr = account.generate_account()
        cls.new_acct_mnemonic = mnemonic.from_private_key(cls.new_acct_priv_key)
        cls.user_acct_mnemonic = mnemonic.from_private_key(cls.user_acct_priv_key)        
        print("Generated new account: "+cls.new_acct_addr)
        print('Privatekey new account: '+cls.new_acct_priv_key )
        print("Generated user account: "+cls.user_acct_addr)
        print('Privatekey user account: '+cls.user_acct_priv_key )
        cls.app_index = 0
        cls.asset_id = 0
        cls.voteBegin = 0
    
    #Test dispence
    def test_1_fund_account(self):
        amt = 2000000
        amtu = 1000000
        fund_new_acct(TestContract.algod_client, TestContract.new_acct_addr, amt, TestContract.funding_acct_mnemonic)
        fund_new_acct(TestContract.algod_client, TestContract.user_acct_addr, amtu, TestContract.funding_acct_mnemonic) 
        print("Funded {amt} to new account for the purpose of deploying contract".format(amt = amt))
        print("Funded {amtu} to a voting account for the purpose of voting yes/no".format(amtu = amtu))
        self.assertGreaterEqual(TestContract.algod_client.account_info(TestContract.new_acct_addr).get('amount'),amt)
        self.assertGreaterEqual(TestContract.algod_client.account_info(TestContract.user_acct_addr).get('amount'),amtu)
    
    #Create ASA named ENB
    def test_2_create_enb(self):
        creator_private_key = get_private_key_from_mnemonic(TestContract.new_acct_mnemonic)
        user_private_key = get_private_key_from_mnemonic(TestContract.user_acct_mnemonic)

        # create asset named ENB
        TestContract.asset_id = Create_asset(TestContract.algod_client,creator_private_key)
        # Opt-in to the asset
        Opt_in(TestContract.algod_client,user_private_key,TestContract.asset_id)
        # Transfer to the Opted address
        Transfer_asset(TestContract.algod_client,creator_private_key,TestContract.user_acct_addr,TestContract.asset_id)
        name = TestContract.algod_indexer.asset_info(TestContract.asset_id)['asset']['params']['name']
        #print('Name: {}'.format(name))
        self.assertEqual(name,'ENB')
        

    #Methods for test cases must start with test
    def test_3_deploy_app(self):
        creator_private_key = get_private_key_from_mnemonic(TestContract.new_acct_mnemonic)

        # declare application state storage (immutable)
        local_ints = 1
        local_bytes = 1
        global_ints = (
            8  # 5 for setup + 3 for choices. Use a larger number for more choices.
        )
        global_bytes = 1
        global_schema = transaction.StateSchema(global_ints, global_bytes)
        local_schema = transaction.StateSchema(local_ints, local_bytes)


        # get PyTeal approval program
        approval_program_ast = approval_program()
        # compile program to TEAL assembly
        approval_program_teal = compileTeal(
            approval_program_ast, mode=Mode.Application, version=6
        )
        # compile program to binary
        approval_program_compiled = compile_program(TestContract.algod_client, approval_program_teal)

        # get PyTeal clear state program
        clear_state_program_ast = clear_state_program()
        # compile program to TEAL assembly
        clear_state_program_teal = compileTeal(
            clear_state_program_ast, mode=Mode.Application, version=6
        )
        # compile program to binary
        clear_state_program_compiled = compile_program(
            TestContract.algod_client, clear_state_program_teal
        )

        # configure registration and voting period
        status = TestContract.algod_client.status()
        regBegin = status["last-round"] + 10
        regEnd = regBegin + 10
        voteBegin = regEnd + 1
        voteEnd = voteBegin + 10

        print(f"Registration rounds: {regBegin} to {regEnd}")
        print(f"Vote rounds: {voteBegin} to {voteEnd}")

        # create list of bytes for app args
        app_args = [
            intToBytes(regBegin),
            intToBytes(regEnd),
            intToBytes(voteBegin),
            intToBytes(voteEnd),
            intToBytes(TestContract.asset_id)
        ]
        
        # create new application
        TestContract.app_index = create_app(
            TestContract.algod_client,
            creator_private_key,
            approval_program_compiled,
            clear_state_program_compiled,
            global_schema,
            local_schema,
            app_args,
        )

        print("Deployed new app with APP ID: "+str(TestContract.app_index))

        global_state = read_global_state(
                TestContract.algod_client, account.address_from_private_key(creator_private_key), TestContract.app_index
            )
        
        self.assertEqual(global_state['RegBegin'], regBegin)
        self.assertEqual(global_state['RegEnd'], regEnd)
        self.assertEqual(global_state['VoteBegin'], voteBegin)
        self.assertEqual(global_state['VoteEnd'], voteEnd)
        self.assertEqual(global_state['AssetID'], TestContract.asset_id)
       
        
    #Test app Optin
    def test_4_optin_app(self):        
        global_state = read_global_state(TestContract.algod_client, TestContract.new_acct_addr, TestContract.app_index)
        # wait for registration period to start
        wait_for_round(TestContract.algod_client,global_state['RegBegin'])
        # opt-in to application
        opt_in_app(TestContract.algod_client, TestContract.user_acct_priv_key, TestContract.app_index)
        account_info = TestContract.algod_client.account_application_info(TestContract.user_acct_addr,TestContract.app_index)
        #print('AccountInfo: {}'.format(account_info))
        self.assertEqual(account_info['app-local-state']['schema']['num-byte-slice'],1)
        self.assertEqual(account_info['app-local-state']['schema']['num-uint'],1)
        
    #Test app call voting
    def test_5_app_call(self):
        global_state = read_global_state(TestContract.algod_client, TestContract.new_acct_addr, TestContract.app_index)
        # wait for registration period to start
        wait_for_round(TestContract.algod_client,global_state['VoteBegin'])
        # call application with arguments
        call_app(TestContract.algod_client, TestContract.user_acct_priv_key, TestContract.app_index, [b"vote", b"yes"],[TestContract.user_acct_addr],[TestContract.asset_id])

        # read local state of application from user account
        #read_local_state(TestContract.algod_client,TestContract.user_acct_addr,TestContract.app_index)
        local_state = read_local_state(TestContract.algod_client,TestContract.user_acct_addr,TestContract.app_index)
        #print('Local_state: ',local_state)
        self.assertEqual(local_state['voted'],'yes')
        # wait for registration period to start
        wait_for_round(TestContract.algod_client,global_state['VoteEnd'])
        

    #Test winning vote
    def test_6_winner(self):
        
        global_state = read_global_state(TestContract.algod_client, TestContract.new_acct_addr, TestContract.app_index)

        max_votes = 0
        max_votes_choice = None
        for key, value in global_state.items():
            if key not in (
                "RegBegin",
                "RegEnd",
                "VoteBegin",
                "VoteEnd",
                "Creator",
                "AssetID"
            ) and isinstance(value, int):
                if value > max_votes:
                    max_votes = value
                    max_votes_choice = key
        
        print("The winner is:", max_votes_choice)

        self.assertEqual(max_votes_choice,'yes')

    #Delete and clear app
    def test_7_delete_app(self):
        # delete application
        delete_app(TestContract.algod_client,TestContract.new_acct_priv_key,TestContract.app_index)
        # clear application from user account
        clear_app(TestContract.algod_client,TestContract.user_acct_priv_key,TestContract.app_index)

def tearDownClass(self) -> None:
    return super().tearDown()

if __name__ == '__main__':
    unittest.main()