# assets/ —— 媒体资源目录

存放节目对应的音视频文件（mp4 / mkv / wav 等）。

- **不进 git**（体积大，已在根 .gitignore 忽略；本 README 除外）
- 部署时用 scp 上板，与仓库目录同构：
  `scp assets/*.mp4 topeet@192.168.31.236:~/LIGHT-BELT/assets/`
- 文件名建议与 show_id 一致，便于对照
- show_id → 媒体/灯效的映射统一登记在 `data/shows_manifest.json`
  （格式见 `host_services/shows_manifest.example.json`）
