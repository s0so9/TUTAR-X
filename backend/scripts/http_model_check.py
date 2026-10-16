"""HTTP üzerinden model doğrulama - backend çalışıyor olmalı."""
import requests
import json

# Backend'e prediction request gönder
response = requests.get("http://localhost:8000/api/v1/predictions/fotmob_5795469")

if response.status_code == 200:
    data = response.json()
    
    print("="*80)
    print("7-MODEL ARCHITECTURE VALIDATION (via HTTP)")
    print("="*80)
    print()
    
    # Model execution summary varsa al
    if "model_execution_summary" in data:
        summary = data["model_execution_summary"]
        
        print(f"Successful Models: {summary.get('successful_count', 0)}")
        print(f"Unavailable Models: {summary.get('unavailable_count', 0)}")
        print(f"Failed Models: {summary.get('failed_count', 0)}")
        print()
        
        if "successful_models" in summary:
            print("SUCCESSFUL MODELS:")
            for model in summary["successful_models"]:
                print(f"  ✓ {model}")
        
        if "unavailable_models" in summary:
            print("\nUNAVAILABLE MODELS:")
            for model in summary["unavailable_models"]:
                print(f"  ✗ {model}")
        
        if "failed_models" in summary and summary["failed_models"]:
            print("\nFAILED MODELS:")
            for model in summary["failed_models"]:
                print(f"  ✗ {model}")
    
    # Version metadata'dan model listesi
    elif "version_metadata" in data and "participating_models" in data["version_metadata"]:
        models = data["version_metadata"]["participating_models"]
        print(f"Participating Models: {len(models)}")
        for model in models:
            print(f"  ✓ {model['model_id']} v{model['version']}")
    
    else:
        print("Response içinde model detayları bulunamadı")
        print(f"Available keys: {list(data.keys())}")

else:
    print(f"ERROR: HTTP {response.status_code}")
    print(response.text)
