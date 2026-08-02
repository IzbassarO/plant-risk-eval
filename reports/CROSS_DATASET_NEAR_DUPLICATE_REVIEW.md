# Cross-Dataset Near-Duplicate Review

**Training source:** PlantVillage (color) @ `9e97599868962bd0079b8db4b7f1efa9185fa1e7`  
**Evaluation source:** PlantDoc @ `5467f6012d78d1c446145d5f582da6096f852ae8`  
**Algorithm / threshold:** imagehash.phash / Hamming <= 6  

Near-duplicates (0 < Hamming <= threshold) are **not** automatically treated as true duplicates. Each pair below is `review_status=pending` and must be adjudicated by a human before the leakage gate may pass.

**16 near-duplicate pair(s) pending review.**

| # | Train class | Train path | Eval class | Eval path | d | status |
|---|---|---|---|---|---|---|
| 1 | Apple___healthy | `raw/color/Apple___healthy/f09b090f-bff1-4fc9-87ad-1b9e05373698___RS_HL 6035.JPG` | Tomato leaf late blight | `train/Tomato leaf late blight/TomatoLateBlightTop.jpg` | 4 | pending |
| 2 | Apple___Black_rot | `raw/color/Apple___Black_rot/888c8b6e-55cb-4492-b489-22f3624f1c39___JR_FrgE.S 8765.JPG` | Apple leaf | `train/Apple leaf/depositphotos_30057617-Green-leaf-of-apple-tree.jpg` | 6 | pending |
| 3 | Blueberry___healthy | `raw/color/Blueberry___healthy/bafd9520-a306-441b-8f0f-8fdd5ff0f3d3___RS_HL 2375.JPG` | Apple leaf | `test/Apple leaf/apple-leaf-closeup-37636177.jpg` | 6 | pending |
| 4 | Cherry_(including_sour)___healthy | `raw/color/Cherry_(including_sour)___healthy/01958ee7-f585-4956-90aa-a40dc79102d4___JR_HL 9836.JPG` | Apple leaf | `train/Apple leaf/depositphotos_30057617-Green-leaf-of-apple-tree.jpg` | 6 | pending |
| 5 | Cherry_(including_sour)___healthy | `raw/color/Cherry_(including_sour)___healthy/6ae3fb47-fad5-4167-b106-782bc5ef68d6___JR_HL 9513.JPG` | Tomato leaf late blight | `train/Tomato leaf late blight/TomatoLateBlightTop.jpg` | 6 | pending |
| 6 | Grape___Black_rot | `raw/color/Grape___Black_rot/69b68016-b0a9-437f-b8a2-3cec7b1ced89___FAM_B.Rot 0370.JPG` | Apple rust leaf | `train/Apple rust leaf/car-apple9.jpg` | 6 | pending |
| 7 | Orange___Haunglongbing_(Citrus_greening) | `raw/color/Orange___Haunglongbing_(Citrus_greening)/81a2842a-0d85-4521-b425-b8ce671553c6___CREC_HLB 5626.JPG` | Apple leaf | `train/Apple leaf/depositphotos_30057617-Green-leaf-of-apple-tree.jpg` | 6 | pending |
| 8 | Orange___Haunglongbing_(Citrus_greening) | `raw/color/Orange___Haunglongbing_(Citrus_greening)/c064d3a5-c0b6-4cc9-8c4b-bbf19f23cba2___CREC_HLB 5331.JPG` | Apple leaf | `train/Apple leaf/depositphotos_30057617-Green-leaf-of-apple-tree.jpg` | 6 | pending |
| 9 | Soybean___healthy | `raw/color/Soybean___healthy/09ae1b30-a83d-40d0-aca4-db6bfcc26bc2___RS_HL 4094.JPG` | Apple leaf | `train/Apple leaf/depositphotos_30057617-Green-leaf-of-apple-tree.jpg` | 6 | pending |
| 10 | Soybean___healthy | `raw/color/Soybean___healthy/2f0e30c3-e2fc-4108-bb9a-c0ac42b4bb9a___RS_HL 4551.JPG` | Apple leaf | `train/Apple leaf/green-leaf-apple-tree-isolated-white-background-33032695.jpg` | 6 | pending |
| 11 | Soybean___healthy | `raw/color/Soybean___healthy/7adac6f5-49f5-4cda-8425-e15d7d821b88___RS_HL 4395.JPG` | Apple leaf | `train/Apple leaf/green-leaf-apple-tree-isolated-white-background-33032695.jpg` | 6 | pending |
| 12 | Soybean___healthy | `raw/color/Soybean___healthy/8e3f6573-c338-48e5-bfba-257daff8e52e___RS_HL 5048.JPG` | Apple leaf | `train/Apple leaf/depositphotos_45748597-stock-photo-ripe-apple-with-leaf.jpg` | 6 | pending |
| 13 | Soybean___healthy | `raw/color/Soybean___healthy/a7711242-c374-4156-a8ba-d1ad73d38f8e___RS_HL 3713.JPG` | Apple leaf | `train/Apple leaf/green-leaf-apple-tree-isolated-white-background-33032695.jpg` | 6 | pending |
| 14 | Soybean___healthy | `raw/color/Soybean___healthy/c16247cc-3f42-43a3-bbca-f1e6fa8e4ee2___RS_HL 4919.JPG` | Apple leaf | `train/Apple leaf/green-leaf-picture-id177130309?b=1&k=6&m=177130309&s=612x612&w=0&h=VP3U0AM5j0fvQqOwuI5f7cmb2Ji88mVep0eoXQaJRfs=.jpg` | 6 | pending |
| 15 | Soybean___healthy | `raw/color/Soybean___healthy/cacad82a-11e3-4252-8ca5-8384ac71b660___RS_HL 4222.JPG` | Apple leaf | `train/Apple leaf/green-leaf-picture-id177130309?b=1&k=6&m=177130309&s=612x612&w=0&h=VP3U0AM5j0fvQqOwuI5f7cmb2Ji88mVep0eoXQaJRfs=.jpg` | 6 | pending |
| 16 | Tomato___Late_blight | `raw/color/Tomato___Late_blight/3de67462-9ae4-455d-8d0d-a625c92c7120___RS_Late.B 5148.JPG` | Tomato leaf late blight | `train/Tomato leaf late blight/TomatoLateBlightTop.jpg` | 6 | pending |
