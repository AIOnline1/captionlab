param(
  [string]$Image = "aliinha/ugc-pipeline:captions-v3",
  [string]$Dockerfile = "Dockerfile.captions.patch"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

docker build --platform linux/amd64 -f $Dockerfile -t $Image .
docker push $Image

Write-Host "Published $Image"
Write-Host "Create a RunPod Serverless Flex endpoint from this image with:"
Write-Host "  GPU: A4000/A4500 16GB pool"
Write-Host "  Workers min: 0"
Write-Host "  Workers max: 1"
Write-Host "  Idle timeout: 5 seconds"
Write-Host "  Execution timeout: 300 seconds"
Write-Host "  Environment: CAPTION_MODEL=large-v3; CAPTION_DEVICE=cuda; CAPTION_COMPUTE_TYPE=float16"
Write-Host "Then set CAPTION_RUNPOD_ENDPOINT_ID and CAPTION_RUNPOD_API_KEY in the gateway environment."
