import requests

url = "https://toncenter.com/api/v3/runGetMethod"

body = {
  "address": "EQAzb42FJ9Jl3hznJiE1wMv-uYnArKs079cwjJq7CY46n_4M",
  "method": "get_jetton_data",
  "stack": []
}

resp = requests.post(url, json=body)

print(resp.json())