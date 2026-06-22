from walrusos.adapters.sui import SuiIdentityAdapter

def main():
    print("--- WalrusOS Identity & Capabilities Example ---")
    
    try:
        identity = SuiIdentityAdapter()
        address = identity.login()
        print(f"Logged in successfully. Active Wallet: {address}")
        
        # Note: Executing PTBs requires a compiled Move package ID deployed on testnet.
        # This example assumes a mock package ID.
        PACKAGE_ID = "0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8" 
        
        print("\nCreating new Workspace on Sui Testnet...")
        if PACKAGE_ID and PACKAGE_ID != "0x0":
            res = identity.create_workspace("Research Org", PACKAGE_ID)
            print(res)
        else:
            print("Skipping PTB execution (Package ID is 0x0).")
            
    except Exception as e:
        print(f"Please run `sui client new-env` to initialize your wallet. Error: {e}")

if __name__ == "__main__":
    main()
