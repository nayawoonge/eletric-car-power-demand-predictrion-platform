import torch

print("=" * 60)
print("PyTorch GPU 설치 확인")
print("=" * 60)

print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"CUDA version: {torch.version.cuda}")
    print(f"Device count: {torch.cuda.device_count()}")
    print(f"Current device: {torch.cuda.current_device()}")
    print(f"Device name: {torch.cuda.get_device_name(0)}")
    
    # GPU 메모리 정보
    total_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"GPU memory: {total_memory:.2f} GB")
    
    # 간단한 텐서 연산 테스트
    x = torch.randn(1000, 1000).cuda()
    y = torch.randn(1000, 1000).cuda()
    z = torch.mm(x, y)
    print(f"\n✅ GPU 텐서 연산 테스트 성공!")
    print(f"   결과 텐서 shape: {z.shape}")
    print(f"   결과 텐서 device: {z.device}")
else:
    print("\n⚠️  CUDA를 사용할 수 없습니다. CPU 모드로 실행됩니다.")

print("=" * 60)
