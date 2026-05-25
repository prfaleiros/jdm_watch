#!/bin/bash
# Seed script for Shipment W2604109729
# 12 items: 10 watches + 2 parts (buckle + donor watch)
# FX rate: 151.7 JPY/USD (from today's card charge 38179/251.66)
# Buyee fees at new April rate: plan 500, service 500
# Except items purchased before April 1 had service fee 300

API="https://uh12il7szl.execute-api.us-east-1.amazonaws.com/prod"
KEY="ejrdmBuyMn5cegzW4NDvS11b9XCkAL9zaWLhhYnt"  # <-- PASTE YOUR API KEY

H1="x-api-key: $KEY"
H2="Content-Type: application/json"

post() { curl -s -X POST "$API$1" -H "$H1" -H "$H2" -d "$2"; echo; }

echo "=== Creating 10 watches ==="

echo "--- 1. Brightz Auto 4S27A movement (personal, junk) ---"
post "/watches" '{
  "brand":"Seiko","collection":"Brightz","reference":"4S27A",
  "case_material":"Titanium","solar":false,"radio_sync":false,
  "auction_price_jpy":10651,"auction_price_usd":70.18,
  "buyee_platform_jpy":0,"buyee_inspection_jpy":500,"domestic_shipping_jpy":230,
  "customs_duty_usd":10.53,
  "current_status":"in_transit_us","is_personal":true,
  "notes":"Junk automatic movement only. Long-term personal project."
}'

echo "--- 2. Lord Matic 5606-8110 (personal) ---"
post "/watches" '{
  "brand":"Seiko","collection":"Lord Matic","reference":"5606-8110",
  "case_material":"Stainless Steel","solar":false,"radio_sync":false,
  "auction_price_jpy":15000,"auction_price_usd":98.88,
  "buyee_platform_jpy":500,"buyee_inspection_jpy":300,"domestic_shipping_jpy":880,
  "customs_duty_usd":14.83,
  "current_status":"in_transit_us","is_personal":true,
  "notes":"Scratched crystal. Running. Pure belt original."
}'

echo "--- 3. Spirit Chrono SBTR011 8T63-00D0 (flip, mint w/ box) ---"
post "/watches" '{
  "brand":"Seiko","collection":"Spirit","reference":"8T63-00D0","jdm_model":"SBTR011",
  "case_material":"Stainless Steel","solar":false,"radio_sync":false,"color":"Black",
  "auction_price_jpy":15400,"auction_price_usd":101.52,
  "buyee_platform_jpy":500,"buyee_inspection_jpy":300,"domestic_shipping_jpy":900,
  "customs_duty_usd":15.23,
  "current_status":"in_transit_us","is_personal":false,
  "notes":"Mint condition with box, papers, manual. Quartz chrono."
}'

echo "--- 4. Brightz 7B24-0BH0 unit 2 ---"
post "/watches" '{
  "brand":"Seiko","collection":"Brightz","reference":"7B24-0BH0","jdm_model":"SAGZ081",
  "diameter_mm":39,"lug_to_lug_mm":46,"thickness_mm":8.8,"lug_width_mm":20,
  "case_material":"Titanium","solar":true,"radio_sync":true,"color":"Deep Blue",
  "auction_price_jpy":12333,"auction_price_usd":81.30,
  "buyee_platform_jpy":500,"buyee_inspection_jpy":500,"domestic_shipping_jpy":350,
  "customs_duty_usd":12.19,
  "current_status":"in_transit_us","is_personal":false,
  "notes":"Second unit. Auction ID g1224836276."
}'

echo "--- 5. Seiko 5 7S26-03S0 ---"
post "/watches" '{
  "brand":"Seiko","collection":"Seiko 5","reference":"7S26-03S0",
  "case_material":"Stainless Steel","solar":false,"radio_sync":false,
  "auction_price_jpy":9622,"auction_price_usd":63.43,
  "buyee_platform_jpy":500,"buyee_inspection_jpy":500,"domestic_shipping_jpy":1010,
  "customs_duty_usd":9.51,
  "current_status":"in_transit_us","is_personal":false,
  "notes":"Automatic."
}'

echo "--- 6. Seiko 7N43-9090 day-date ---"
post "/watches" '{
  "brand":"Seiko","collection":"Unknown","reference":"7N43-9090",
  "case_material":"Stainless Steel","solar":false,"radio_sync":false,"color":"Ivory",
  "auction_price_jpy":6875,"auction_price_usd":45.32,
  "buyee_platform_jpy":500,"buyee_inspection_jpy":500,"domestic_shipping_jpy":990,
  "customs_duty_usd":6.80,
  "current_status":"in_transit_us","is_personal":false,
  "notes":"Quartz day-date. Silver round case."
}'

echo "--- 7. Spirit Chrono 7T92 SBTQ043 (NOS) ---"
post "/watches" '{
  "brand":"Seiko","collection":"Spirit","reference":"7T92","jdm_model":"SBTQ043",
  "case_material":"Stainless Steel","solar":false,"radio_sync":false,"color":"Black",
  "auction_price_jpy":13800,"auction_price_usd":90.97,
  "buyee_platform_jpy":500,"buyee_inspection_jpy":500,"domestic_shipping_jpy":750,
  "customs_duty_usd":13.65,
  "current_status":"in_transit_us","is_personal":false,
  "notes":"New old stock. 1/20 sec chrono."
}'

echo "--- 8. Liner vintage hand-wind (personal) ---"
post "/watches" '{
  "brand":"Seiko","collection":"Liner","reference":"unknown",
  "case_material":"Stainless Steel","solar":false,"radio_sync":false,
  "auction_price_jpy":24800,"auction_price_usd":163.48,
  "buyee_platform_jpy":500,"buyee_inspection_jpy":500,"domestic_shipping_jpy":840,
  "customs_duty_usd":24.52,
  "current_status":"in_transit_us","is_personal":true,
  "notes":"Rare vintage hand-wind. Deadstock. 101% emotional purchase. Decides Harmony fate."
}'

echo "--- 9. Brightz 7B24-0BH0 unit 3 ---"
post "/watches" '{
  "brand":"Seiko","collection":"Brightz","reference":"7B24-0BH0","jdm_model":"SAGZ081",
  "diameter_mm":39,"lug_to_lug_mm":46,"thickness_mm":8.8,"lug_width_mm":20,
  "case_material":"Titanium","solar":true,"radio_sync":true,"color":"Deep Blue",
  "auction_price_jpy":14000,"auction_price_usd":92.29,
  "buyee_platform_jpy":500,"buyee_inspection_jpy":500,"domestic_shipping_jpy":380,
  "customs_duty_usd":13.84,
  "current_status":"in_transit_us","is_personal":false,
  "notes":"Third unit. Auction ID m1225264645."
}'

echo "--- 10. Seiko 7B22-HAB0 solar radio ---"
post "/watches" '{
  "brand":"Seiko","collection":"Brightz","reference":"7B22-HAB0",
  "case_material":"Titanium","solar":true,"radio_sync":true,"color":"Silver",
  "auction_price_jpy":3789,"auction_price_usd":24.98,
  "buyee_platform_jpy":500,"buyee_inspection_jpy":500,"domestic_shipping_jpy":930,
  "customs_duty_usd":3.75,
  "current_status":"in_transit_us","is_personal":false,
  "notes":"JJY only radio sync. Needs emulator for US use."
}'

echo ""
echo "=== COPY THE WATCH IDs FROM ABOVE ==="
echo "Then replace placeholders below and press Enter."
read

echo "=== Creating shipment W2604109729 ==="
echo "Note: parts excluded from allocation. Their shipping share (~$3.60 total) is absorbed by watches — negligible."
post "/shipments" '{
  "total_cost_usd": 64.57,
  "total_cost_jpy": 9796,
  "weight_g": 1570,
  "carrier": "DHL",
  "ship_date": "2026-04-11",
  "notes": "W2604109729. 10 watches + 2 parts (buckle + donor). Customs 20193 JPY.",
  "watch_ids": [
    {"watch_id": "4S27A_ID", "auction_price_jpy": 10651},
    {"watch_id": "LM_ID", "auction_price_jpy": 15000},
    {"watch_id": "SPIRIT8T63_ID", "auction_price_jpy": 15400},
    {"watch_id": "BH0_2_ID", "auction_price_jpy": 12333},
    {"watch_id": "SEIKO5_ID", "auction_price_jpy": 9622},
    {"watch_id": "7N43_ID", "auction_price_jpy": 6875},
    {"watch_id": "SPIRIT7T92_ID", "auction_price_jpy": 13800},
    {"watch_id": "LINER_ID", "auction_price_jpy": 24800},
    {"watch_id": "BH0_3_ID", "auction_price_jpy": 14000},
    {"watch_id": "7B22_ID", "auction_price_jpy": 3789}
  ]
}'

echo ""
echo "=== Allocate shipping ==="
echo "Replace SHIPMENT_ID below"
post "/shipments/SHIPMENT_ID/allocate" '{}'

echo ""
echo "=== Add parts as additional costs ==="

echo "--- Lukia buckle -> Exceline bf1f1cc8 ---"
echo "Buckle 2981 + dom 930 + svc 500 + customs ~447 + intl ship alloc ~218 = ~5076 JPY = ~$33.47"
post "/watches/bf1f1cc8/costs" '{
  "amount_usd": 33.47,
  "category": "part",
  "notes": "Seiko Lukia 11mm silver buckle. Auction j1200159431. Includes domestic ship, service fee, customs and intl ship allocation."
}'

echo "--- Citizen xC donor -> H330 d133fd04 ---"
echo "Donor 4540 + svc 500 + customs ~681 + intl ship alloc ~332 = ~6053 JPY = ~$39.90"
post "/watches/d133fd04/costs" '{
  "amount_usd": 39.90,
  "category": "part",
  "notes": "Citizen xC H330-T008658 donor watch from Mercari (M26040803977). Bought for parts to repair bench unit. Includes service fee, customs and intl ship allocation."
}'

echo ""
echo "=== DONE ==="
echo "Total watches in system should now be 20."
echo "Verify: curl \"\$API/watches\" -H \"x-api-key: \$KEY\""