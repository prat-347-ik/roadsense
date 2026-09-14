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
    print(f"\n================ TOTAL INCIDENTS: {len(incidents)} ================\n")

    for inc in incidents:
        inc_id = inc["id"]
        detail = client.get(f'http://127.0.0.1:8000/v1/incidents/{inc_id}', headers=headers).json()
        print(f"Incident #{inc_id}:")
        print(f"  Violation Type:    {detail['violation_type']}")
        print(f"  Status:            {detail['status']}")
        print(f"  Rejection Reason:  {detail.get('rejection_reason')}")
        print(f"  Rejection Details: {detail.get('rejection_details')}")
        print(f"  Observations ({len(detail['observations'])}):")
        for o in detail['observations']:
            print(f"    - Device: {o['device_id']}, Coords: ({o['lat']}, {o['lon']}), wrong_way: {o['wrong_way_status']}, rej_reason: {o.get('rejection_reason')}")
        print(f"  Evidence items:    {len(detail['evidence_items'])}")
        print("-" * 60)

if __name__ == "__main__":
    main()
