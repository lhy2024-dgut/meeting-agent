ASR 测试音频说明
================

terms_test.wav
  专有名词识别率测试音频（约 30-60s）
  包含 10 个专有名词：实验室名、人名、项目代号等

terms_test_ref.txt
  对应的正确转录文本（UTF-8）

使用方法：
  python tests/test_wer.py \
    --audio tests/fixtures/audio/terms_test.wav \
    --ref-file tests/fixtures/audio/terms_test_ref.txt \
    --terms "术语1,术语2,...,术语10" \
    --no-terms

说明：
  --no-terms 开关会先跑不加词表的基线，再跑加词表版本，方便对比识别率提升幅度。
