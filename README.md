# JDM Watch Business — Serverless Inventory & Pricing System

## Prerequisites
- AWS CLI configured with an IAM user (NOT root)
- Python 3.12+
- AWS CDK v2: `npm install -g aws-cdk`
- CDK bootstrapped: `cdk bootstrap aws://ACCOUNT_ID/us-east-1`

## Deploy

```bash
cd cdk
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cdk synth
cdk deploy
```

Note the outputs — you'll need the API URL and API key.

### Get your API key value
```bash
aws apigateway get-api-keys --include-values --query "items[?name=='JdmWatchBusiness-WatchApiKey*'].value" --output text
```

## Upload config
```bash
aws s3 cp config/fees.csv s3://jdm-watch-config-ACCOUNT_ID/fees.csv
```

## Seed existing inventory
```bash
cd scripts
python seed.py --file seed_inventory.csv --table WatchBusiness
```

## API Usage

All requests require header: `x-api-key: YOUR_KEY`

### Create a watch
```bash
curl -X POST $API_URL/watches \
  -H "x-api-key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "brand": "Seiko", "collection": "Brightz",
    "reference": "7B24-0BH0", "jdm_model": "SAGZ081",
    "case_material": "Titanium", "solar": true, "radio_sync": true,
    "color": "Deep Blue", "diameter_mm": 39,
    "auction_price_jpy": 23570, "auction_price_usd": 149.04,
    "customs_duty_usd": 22.36, "current_status": "listed"
  }'
```

### List watches by status
```bash
curl "$API_URL/watches?status=on_bench" -H "x-api-key: $KEY"
curl "$API_URL/watches" -H "x-api-key: $KEY"  # all watches
```

### Log a stage transition (with hours and notes)
```bash
curl -X POST $API_URL/watches/WATCH_ID/transitions \
  -H "x-api-key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "to_status": "on_bench",
    "hours_spent": 0.75,
    "notes": "Ultrasonic cleaned bracelet. Crown tube had gunk, 10min cleaning."
  }'
```

### Log same-stage work (journal entry)
```bash
curl -X POST $API_URL/watches/WATCH_ID/transitions \
  -H "x-api-key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "to_status": "on_bench",
    "hours_spent": 0.5,
    "notes": "Radio sync test passed. Replaced crystal — old one had chip."
  }'
```

### Add extra cost
```bash
curl -X POST $API_URL/watches/WATCH_ID/costs \
  -H "x-api-key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "amount_usd": 10.00,
    "category": "part",
    "notes": "Replacement sapphire crystal from eBay"
  }'
```

### Get pricing tiers
```bash
curl "$API_URL/watches/WATCH_ID/pricing" -H "x-api-key: $KEY"
```

### Calculate max bid before auction
```bash
curl -X POST $API_URL/pricing/max-bid \
  -H "x-api-key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "expected_sale_usd": 350,
    "fx_rate": 150,
    "labor_hours_estimate": 1.5,
    "repair_estimate_usd": 0,
    "pieces_in_shipment": 3
  }'
```

### Create a shipment and allocate costs
```bash
# Create shipment with linked watches
curl -X POST $API_URL/shipments \
  -H "x-api-key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "total_cost_usd": 53.50,
    "weight_g": 720,
    "dimensions": "31x34x12cm",
    "carrier": "DHL",
    "watch_ids": [
      {"watch_id": "abc123", "auction_price_jpy": 6500},
      {"watch_id": "def456", "auction_price_jpy": 23570},
      {"watch_id": "ghi789", "auction_price_jpy": 8550}
    ]
  }'

# Trigger weighted allocation
curl -X POST $API_URL/shipments/SHIPMENT_ID/allocate -H "x-api-key: $KEY"
```

### Generate listing report
```bash
curl "$API_URL/watches/WATCH_ID/listing-report" -H "x-api-key: $KEY"
```

### Upload a photo
```bash
# Get presigned URL
curl "$API_URL/watches/WATCH_ID/upload-url?filename=01_dial.jpg" -H "x-api-key: $KEY"

# Upload using the returned URL
curl -X PUT -H "Content-Type: image/jpeg" --upload-file dial.jpg "PRESIGNED_URL"
```

## Photo naming convention
```
photos/{watch_id}/01_dial.jpg
photos/{watch_id}/02_caseback.jpg
photos/{watch_id}/03_side_crown.jpg
photos/{watch_id}/04_bracelet.jpg
photos/{watch_id}/05_clasp.jpg
photos/{watch_id}/06_lume.jpg
photos/{watch_id}/07_wrist.jpg
photos/{watch_id}/timestamp.jpg      # always last, take right before listing
```

## Export for Power BI
```bash
cd scripts
python export.py --table WatchBusiness --output watches.csv
```

## Updating fees
Edit `config/fees.csv` and re-upload to S3. Changes take effect on next Lambda cold start (or deploy).
