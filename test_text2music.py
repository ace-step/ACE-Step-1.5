import requests, time

data = {
    "prompt": "high energy drum and bass",
    "lyrics": "[Instrumental]",
    "audio_duration": 6.0,
    "task_type": "text2music",
    "inference_steps": 8,
    "guidance_scale": 7.0,
    "thinking": False,
    "batch_size": 1,
    "audio_format": "wav",
    "vocal_language": "en"
}
res = requests.post("http://127.0.0.1:8001/release_task", json=data)
if res.json()['code'] == 200:
    task_id = res.json()['data']['task_id']
    while True:
        time.sleep(2)
        poll_res = requests.post("http://127.0.0.1:8001/query_result", json={"task_id_list": [task_id]})
        status = poll_res.json()['data'][0]['status']
        print(f"Status: {status}")
        if status in (1, 2):
            print(poll_res.json())
            break
