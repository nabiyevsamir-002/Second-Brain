"""LocalDoc/azerbaijani-whisper-small → CTranslate2 int8, faster-whisper üçün (bir dəfə).

Model `small` ölçüsündədir, amma Azərbaycan dili üçün öyrədilib. transformers və torch yalnız
çevirmə üçün lazımdır, ona görə müvəqqəti konteynerdə işləyir (sirr verilmir). Noutbukda,
~/SecondBrain qovluğunda:

  docker run --rm --memory=4g --cpu-shares=256 -v secondbrain_models:/models \
    -v "$PWD/scripts:/scripts:ro" --entrypoint bash secondbrain-bot:latest -c \
    'pip install -q --no-cache-dir --target /tmp/conv torch --index-url https://download.pytorch.org/whl/cpu \
     && pip install -q --no-cache-dir --target /tmp/conv transformers==5.22.1 \
     && PYTHONPATH=/tmp/conv python /scripts/convert_az_whisper.py'

Sonra .env-də: WHISPER_MODEL=/models/whisper/az-small-ct2
"""

from pathlib import Path

from ctranslate2.converters import TransformersConverter
from huggingface_hub import snapshot_download

REPO = "LocalDoc/azerbaijani-whisper-small"
REVISION = "88c9efdafe6e60e71be0c8c66840db676a255fe8"
OUTPUT = "/models/whisper/az-small-ct2"

source = snapshot_download(REPO, revision=REVISION, allow_patterns=["*.json", "*.safetensors"])
TransformersConverter(source, copy_files=["tokenizer.json"]).convert(
    OUTPUT, quantization="int8", force=True
)
print("hazır:", OUTPUT, sorted(p.name for p in Path(OUTPUT).iterdir()))
