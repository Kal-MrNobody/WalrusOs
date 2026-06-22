#!/bin/bash
# Reference script to deploy the WalrusOS Sui contracts

set -e

echo "Building WalrusOS Move Contracts..."
sui move build --path ./move/walrusos

echo "Deploying to Sui Testnet..."
sui client publish --path ./move/walrusos --gas-budget 100000000

echo "Deployment complete."
