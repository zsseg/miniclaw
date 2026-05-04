# 修复图片识别时机和采信度

## 目标

1. 图片识别慢：先发图、后问“这张图什么意思”时，尽量等识图结果出来再回答。
2. 图片不一定表达真实意思：把识图结果降级为“视觉线索”，不是事实。
3. 没人问图：不要主动解释图片。
4. 有人问图：可以说，但要保守、带不确定性，并结合群友评论。
5. 图片没啥内容：别硬解释。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_image_timing_confidence_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 可调参数

显式问图时等待识图结果的秒数，默认 8 秒，范围会限制在 2~12 秒：

```powershell
$env:QQ_IMAGE_QUESTION_WAIT_SEC="8"
python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_image_timing_confidence .\src\clawmini\tools\qq_auto_reply.py
```
