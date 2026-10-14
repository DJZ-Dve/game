#include "Submarine/Sonar.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Submarine/Submarine.h"
#include "TextureResource.h"

namespace
{
	// 换能器在艇上的位置（Godot 版 SONAR_HEAD = (0, -0.9, -5.2)，艏部下方）：换到艇身局部坐标（厘米）
	const FVector SonarHead(0.f, -520.f, -90.f);
}

USonarComponent::USonarComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	bTickInEditor = false;
}

void USonarComponent::Setup(ASubmarine* InSub)
{
	Sub = InSub;
	Screen = nullptr;
	if (!InSub)
	{
		return;
	}
	Fan.Reset();
	for (int32 k = 0; k < 23; ++k)
	{
		Fan.Add(3.f * FMath::Pow(0.75f, float(k)));
	}
	Fan.Add(0.f);
	Fan.Add(-0.04f);
	Col.SetNumZeroed(Bins);
	Pixels.SetNumZeroed(Bearings * Bins * 4);

	if (!Returns)
	{
		Returns = UTexture2D::CreateTransient(Bearings, Bins, PF_B8G8R8A8, TEXT("SonarReturns"));
		Returns->SRGB = false;
		Returns->Filter = TF_Bilinear;
		Returns->AddressX = TA_Wrap;
		Returns->AddressY = TA_Clamp;
		Returns->UpdateResource();
	}
	UStaticMeshComponent* Mesh = Cast<UStaticMeshComponent>(InSub->FindNode(TEXT("Screen_Sonar")));
	UMaterialInterface* Crt = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Materials/Master/M_SonarCRT.M_SonarCRT"));
	if (Mesh && Crt)
	{
		Screen = Mesh->CreateDynamicMaterialInstance(0, Crt);
		Screen->SetTextureParameterValue(TEXT("returns"), Returns);
		Screen->SetScalarParameterValue(TEXT("gain"), Gain);
		Screen->SetScalarParameterValue(TEXT("cursor_rng"), 37.5f / RangeM);
	}
}

void USonarComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (!Sub.IsValid() || !Returns || !Screen)
	{
		return;
	}
	Sweep = FMath::Fmod(Sweep + DeltaTime / Period, 1.f);
	const int32 Target = FMath::Clamp(int32(Sweep * Bearings), 0, Bearings - 1);
	int32 First = -1;
	int32 Count = 0;
	while (NextCol != Target)
	{
		if (First < 0)
		{
			First = NextCol;
		}
		Ping(NextCol);
		NextCol = (NextCol + 1) % Bearings;
		++Count;
	}
	if (Count > 0)
	{
		// 整张图一起传（256×160，很小）
		FUpdateTextureRegion2D* Region = new FUpdateTextureRegion2D(0, 0, 0, 0, Bearings, Bins);
		TArray<uint8>* Copy = new TArray<uint8>(Pixels);
		Returns->UpdateTextureRegions(0, 1, Region, Bearings * 4, 4, Copy->GetData(),
			[Copy](uint8*, const FUpdateTextureRegion2D* R)
			{
				delete Copy;
				delete R;
			});
	}
	Screen->SetScalarParameterValue(TEXT("sweep"), Sweep);
}

void USonarComponent::Ping(int32 Column)
{
	ASubmarine* S = Sub.Get();
	UWorld* World = S ? S->GetWorld() : nullptr;
	if (!World)
	{
		return;
	}
	// 方位：艏向起顺时针（从上往下看）；UE 里正的偏航就是顺时针
	FVector Fwd = S->GetActorForwardVector();
	Fwd.Z = 0.f;
	Fwd.Normalize();
	const FVector H = Fwd.RotateAngleAxis(360.f * (Column + 0.5f) / Bearings, FVector::UpVector);
	const FVector Origin = S->GetBody()->GetComponentTransform().TransformPosition(SonarHead);
	FCollisionQueryParams Params(TEXT("Sonar"), true, S);

	for (float& V : Col)
	{
		V = 0.f;
	}
	float PrevD = -1.f;
	float PrevS = 0.f;
	bool bPrevHard = false;
	for (float T : Fan)
	{
		const FVector Dir = (H + FVector::DownVector * T).GetSafeNormal();
		FHitResult Hit;
		if (!World->LineTraceSingleByChannel(Hit, Origin, Origin + Dir * RangeM * 100.f, ECC_WorldStatic, Params))
		{
			PrevD = -1.f;
			continue;
		}
		const float D = Hit.Distance / (RangeM * 100.f);
		const FVector N = Hit.ImpactNormal;
		const float Facing = FMath::Abs(FVector::DotProduct(N, -Dir));
		// 海底（包括缓坡）是软泥沙，回波弱；陡的东西（礁石、沉船）当硬目标，迎着声波的那一面回波很强
		const bool bHard = N.Z < 0.35f || (Hit.GetComponent() && Hit.GetComponent()->ComponentHasTag(TEXT("SonarHard")));
		const float Strength = bHard ? (0.7f + 0.6f * Facing) : (0.22f + 0.7f * Facing);
		// 一个点在距离上抹开一点（Godot 版 _splat：本格 1，前后两格 0.45）
		const int32 I = int32(D * Bins);
		for (int32 k = -1; k <= 1; ++k)
		{
			if (I + k >= 0 && I + k < Bins)
			{
				Col[I + k] += Strength * (k == 0 ? 1.f : 0.45f);
			}
		}
		// 相邻两条射线落在同一片海底上：中间这段也是海底，连成一片；前一条打在硬目标上，中间就是它的声影
		if (PrevD >= 0.f && !bPrevHard && !bHard && D > PrevD && D - PrevD < 0.45f)
		{
			const int32 I0 = int32(PrevD * Bins);
			const int32 I1 = int32(D * Bins);
			for (int32 i = I0 + 1; i < I1 && i < Bins; ++i)
			{
				Col[i] += FMath::Lerp(PrevS, Strength, float(i - I0) / (I1 - I0)) * 0.7f;
			}
		}
		PrevD = D;
		PrevS = Strength;
		bPrevHard = bHard;
	}
	for (int32 i = 0; i < Bins; ++i)
	{
		const float R = (i + 0.5f) / Bins;
		float V = Col[i] * FMath::FRandRange(0.4f, 1.3f) * (1.f - 0.3f * R);  // 斑点噪声、传播损失
		V += FMath::FRand() * 0.045f;                                         // 底噪
		if (i < 3)
		{
			V += FMath::FRand() * 0.5f;                                       // 发射余震：中心一小圈
		}
		const uint8 B = uint8(FMath::Clamp(V, 0.f, 1.f) * 255.f);
		uint8* P = &Pixels[(i * Bearings + Column) * 4];
		P[0] = 0;   // B
		P[1] = 0;   // G
		P[2] = B;   // R
		P[3] = 255;
	}
}
