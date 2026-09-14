import httpx

def main():
    client = httpx.Client()
    login_res = client.post('http://127.0.0.1:8000/v1/auth/login', json={
        'email': 'admin@roadsense.local',
        'password': 'roadsense-admin-password'
    }).json()
    token = login_res['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    incidents = client.get('http://127.0.0.1:8000/v1/incidents', headers=headers).json()
    
    print("\n" + "="*80)
    print("ROADSENSE REVIEWER DASHBOARD: LIVE SCENARIO VERIFICATION REPORT")
    print("="*80 + "\n")

    for inc in incidents:
        detail = client.get(f'http://127.0.0.1:8000/v1/incidents/{inc["id"]}', headers=headers).json()
        print(f"Incident ID: #{detail['id']} | Type: {detail['violation_type']} | Status: [{detail['status'].upper()}]")
        print(f"Hashed Plate: {detail['hashed_plate'][:24]}...")
        print(f"Window: {detail['window_start']} -> {detail['window_end']}")
        if detail.get('rejection_reason'):
            print(f"Rejection Reason:  {detail['rejection_reason']}")
            print(f"Rejection Details: {detail['rejection_details']}")
        elif detail['status'] == 'corroborated_no_evidence':
            print(f"Status Diagnostic: {detail.get('rejection_details')}")
        print(f"Observations Count: {len(detail['observations'])}")
        for i, o in enumerate(detail['observations'], 1):
            print(f"  Obs #{i}: Device={o['device_id']}, Coords=({o['lat']:.4f}, {o['lon']:.4f}), wrong_way_status={o['wrong_way_status']}, rejection_reason={o.get('rejection_reason')}")
        print(f"Evidence Items: {len(detail['evidence_items'])}")
        print("-" * 80)

if __name__ == "__main__":
    main()
