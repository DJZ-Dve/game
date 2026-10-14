#include "Submarine/Instruments.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Scene/GuixuSceneAsset.h"
#include "Submarine/Submarine.h"

namespace
{
	/** 指针名 → 满量程转过的角度（Godot 版 GAUGES） */
	const TMap<FName, float>& GaugeSweeps()
	{
		static const TMap<FName, float> M = {
			{TEXT("Depth"), 270.f}, {TEXT("Pressure"), 270.f}, {TEXT("Heading"), 360.f},
			{TEXT("Volt"), 90.f}, {TEXT("Amp"), 90.f}, {TEXT("ThrL"), 90.f}, {TEXT("ThrR"), 90.f},
			{TEXT("Ballast"), 270.f}, {TEXT("Trim"), 270.f}, {TEXT("Temp"), 270.f}, {TEXT("Hum"), 270.f},
			{TEXT("O2"), 90.f}, {TEXT("CO2"), 90.f}, {TEXT("Hyd"), 270.f}, {TEXT("Comp"), 270.f}, {TEXT("O2Tank"), 270.f},
			{TEXT("BatV"), 90.f}, {TEXT("BatA"), 90.f}, {TEXT("Heading2"), 360.f}, {TEXT("Speed"), 270.f}, {TEXT("Ballast2"), 270.f},
			{TEXT("Signal"), 90.f},
		};
		return M;
	}

	// 数码管一格的大小（米）：对着 Godot 版的截图量的（DSEG7 字号 64、像素 0.00028 米）
	constexpr float CellW = 0.0145f;
	constexpr float CellH = 0.022f;
}

UInstrumentsComponent::UInstrumentsComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	bTickInEditor = false;
}

UMaterialInstanceDynamic* UInstrumentsComponent::OwnMaterial(USceneComponent* Node) const
{
	if (UStaticMeshComponent* M = Cast<UStaticMeshComponent>(Node))
	{
		return M->CreateDynamicMaterialInstance(0);
	}
	return nullptr;
}

void UInstrumentsComponent::Setup(ASubmarine* InSub)
{
	Sub = InSub;
	Needles.Reset();
	Displays.Reset();
	Lamps.Reset();
	Warns.Reset();
	WarnState.Reset();
	Floats.Reset();
	if (!InSub)
	{
		return;
	}
	for (const auto& It : GaugeSweeps())
	{
		if (USceneComponent* N = InSub->FindNode(FName(*(TEXT("Needle_") + It.Key.ToString()))))
		{
			FNeedle& G = Needles.Add(It.Key);
			G.Node = N;
			G.Base = N->GetRelativeRotation().Quaternion();
			G.Sweep = It.Value;
			// 指针不投影（Godot 版 Submarine.stop_casting）
			if (UPrimitiveComponent* P = Cast<UPrimitiveComponent>(N))
			{
				P->SetCastShadow(false);
			}
		}
	}

	UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
	UMaterialInterface* SegMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Materials/Master/M_SevenSeg.M_SevenSeg"));
	for (const TCHAR* Name : {TEXT("Depth"), TEXT("Alt"), TEXT("Clock"), TEXT("Log")})
	{
		USceneComponent* Anchor = InSub->FindNode(FName(*(FString(TEXT("Display_")) + Name)));
		if (!Anchor || !Plane || !SegMat)
		{
			continue;
		}
		const bool bClock = FCString::Strcmp(Name, TEXT("Clock")) == 0;
		const int32 Cells = bClock ? 6 : 5;
		UStaticMeshComponent* Q = UGuixuSceneLibrary::AddComponent<UStaticMeshComponent>(InSub, Anchor, FName(*(FString(TEXT("Display_")) + Name + TEXT("_Segs"))));
		Q->SetStaticMesh(Plane);
		Q->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Q->SetCastShadow(false);
		// Godot 的 Label3D 在挂点的 xy 平面里、朝挂点的 +z：换到 UE 是平面的 X 沿挂点 X、法线沿挂点 +Y，平面的 +Y 朝下
		Q->SetRelativeRotation(FRotationMatrix::MakeFromXZ(FVector(1.f, 0.f, 0.f), FVector(0.f, 1.f, 0.f)).Rotator());
		Q->SetRelativeLocation(FVector(0.f, 0.05f, 0.f));
		Q->SetRelativeScale3D(FVector(CellW * Cells, CellH, 1.f));
		UMaterialInstanceDynamic* M = Q->CreateDynamicMaterialInstance(0, SegMat);
		M->SetScalarParameterValue(TEXT("cells"), Cells);
		M->SetScalarParameterValue(TEXT("colon_mask"), bClock ? float((1 << 1) | (1 << 3)) : 0.f);
		FDisplay& D = Displays.Add(Name);
		D.Mat = M;
		D.Cells = Cells;
	}

	for (int32 i = 0; i < 8; ++i)
	{
		if (UMaterialInstanceDynamic* M = OwnMaterial(InSub->FindNode(FName(*FString::Printf(TEXT("Lamp_%d"), i)))))
		{
			Lamps.Add(M);
		}
		if (UMaterialInstanceDynamic* M = OwnMaterial(InSub->FindNode(FName(*FString::Printf(TEXT("Warn_%d"), i)))))
		{
			Warns.Add(M);
			WarnState.Add(0);
		}
	}
	for (const TCHAR* Name : {TEXT("Float_O2a"), TEXT("Float_O2b")})
	{
		if (USceneComponent* N = InSub->FindNode(Name))
		{
			Floats.Add({N, N->GetRelativeLocation(), float(FCString::Strlen(Name))});
			if (UPrimitiveComponent* P = Cast<UPrimitiveComponent>(N))
			{
				P->SetCastShadow(false);
			}
		}
	}
	// 演示用：通信中断灯一直闪（以后由事件系统控制）
	SetWarning(int32(EWarn::Comms), 2);
}

void UInstrumentsComponent::SetWarning(int32 Index, int32 State)
{
	if (WarnState.IsValidIndex(Index))
	{
		WarnState[Index] = State;
	}
}

void UInstrumentsComponent::SetGauge(FName Key, float Target, float DeltaTime)
{
	FNeedle* G = Needles.Find(Key);
	if (!G || !G->Node.IsValid())
	{
		return;
	}
	Target = FMath::Clamp(Target, 0.f, 1.f);
	const float Jitter = (FMath::FRand() - 0.5f) * 0.004f;
	// 弹簧阻尼，让指针有一点惯性
	const float Acc = (Target + Jitter - G->Value) * 40.f - G->Vel * 9.f;
	G->Vel += Acc * DeltaTime;
	G->Value += G->Vel * DeltaTime;
	// Godot：绕局部 +y 转 -sweep·value（顺时针）；换到 UE 是绕局部 +z 转 +sweep·value
	G->Node->SetRelativeRotation(G->Base * FQuat(FVector(0.f, 0.f, 1.f), FMath::DegreesToRadians(G->Sweep * G->Value)));
}

void UInstrumentsComponent::SetDisplay(FName Key, const FString& Text)
{
	FDisplay* D = Displays.Find(Key);
	if (!D || !D->Mat.IsValid())
	{
		return;
	}
	TArray<float> Digits;
	int32 DotAfter = -1;
	for (TCHAR C : Text)
	{
		if (C >= '0' && C <= '9')
		{
			Digits.Add(float(C - '0'));
		}
		else if (C == '-')
		{
			Digits.Add(10.f);
		}
		else if (C == '.')
		{
			DotAfter = Digits.Num() - 1;
		}
		else if (C == ' ')
		{
			Digits.Add(-1.f);
		}
	}
	// 右对齐到 Cells 格
	const int32 Shift = D->Cells - Digits.Num();
	float Cell[9];
	for (int32 i = 0; i < 9; ++i)
	{
		const int32 Src = i - Shift;
		Cell[i] = (i < D->Cells && Digits.IsValidIndex(Src)) ? Digits[Src] : -1.f;
	}
	D->Mat->SetVectorParameterValue(TEXT("digits_a"), FLinearColor(Cell[0], Cell[1], Cell[2], 0.f));
	D->Mat->SetVectorParameterValue(TEXT("digits_b"), FLinearColor(Cell[3], Cell[4], Cell[5], 0.f));
	D->Mat->SetVectorParameterValue(TEXT("digits_c"), FLinearColor(Cell[6], Cell[7], Cell[8], 0.f));
	D->Mat->SetScalarParameterValue(TEXT("dot_after"), DotAfter >= 0 ? float(DotAfter + Shift) : -1.f);
}

void UInstrumentsComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	ASubmarine* S = Sub.Get();
	if (!S)
	{
		return;
	}
	Time += DeltaTime;
	DiveTime += DeltaTime;
	const float T = Time;
	const float Depth = S->Depth();
	const float Thrust = 0.f;  // 开船以后接上推进
	Battery = FMath::Max(3.2f, Battery - DeltaTime * (0.0004f + Thrust * 0.002f));
	Co2 = FMath::Min(3.0f, Co2 + DeltaTime * 0.0008f);

	SetGauge(TEXT("Depth"), Depth / 10000.f, DeltaTime);
	SetGauge(TEXT("Heading"), S->HeadingDeg() / 360.f, DeltaTime);
	SetGauge(TEXT("Pressure"), (1.03f + FMath::Sin(T * 0.1f) * 0.01f) / 2.f, DeltaTime);
	SetGauge(TEXT("Volt"), (Battery * 25.f - Thrust * 6.f) / 150.f, DeltaTime);
	SetGauge(TEXT("Amp"), (12.f + Thrust * 55.f) / 100.f, DeltaTime);
	SetGauge(TEXT("ThrL"), 0.f, DeltaTime);
	SetGauge(TEXT("ThrR"), 0.f, DeltaTime);
	SetGauge(TEXT("Ballast"), 0.62f, DeltaTime);
	SetGauge(TEXT("Trim"), 0.5f + FMath::Sin(T * 0.21f) * 0.02f, DeltaTime);
	SetGauge(TEXT("Temp"), 11.f / 50.f, DeltaTime);
	SetGauge(TEXT("Hum"), (82.f + FMath::Sin(T * 0.05f) * 2.f) / 100.f, DeltaTime);
	SetGauge(TEXT("O2"), (20.6f + FMath::Sin(T * 0.37f) * 0.15f) / 25.f, DeltaTime);
	SetGauge(TEXT("CO2"), Co2 / 5.f, DeltaTime);
	SetGauge(TEXT("Hyd"), 17.5f / 25.f + Thrust * 0.02f, DeltaTime);
	SetGauge(TEXT("Comp"), 0.55f, DeltaTime);
	SetGauge(TEXT("O2Tank"), 13.8f / 25.f, DeltaTime);
	SetGauge(TEXT("BatV"), (Battery * 25.f - Thrust * 6.f) / 150.f, DeltaTime);
	SetGauge(TEXT("BatA"), (18.f + Thrust * 95.f) / 200.f, DeltaTime);
	SetGauge(TEXT("Heading2"), S->HeadingDeg() / 360.f, DeltaTime);
	SetGauge(TEXT("Speed"), 0.f, DeltaTime);
	SetGauge(TEXT("Ballast2"), 0.41f, DeltaTime);
	SetGauge(TEXT("Signal"), 0.15f + FMath::Abs(FMath::Sin(T * 0.13f)) * 0.1f + FMath::FRand() * 0.05f, DeltaTime);

	SetDisplay(TEXT("Depth"), FString::Printf(TEXT("%6.1f"), Depth));
	const float Alt = S->Altitude();
	SetDisplay(TEXT("Alt"), Alt >= 0.f ? FString::Printf(TEXT("%5.1f"), Alt) : FString(TEXT("  ---")));
	SetDisplay(TEXT("Log"), FString::Printf(TEXT("%6.2f"), LogKm + 12.4f));
	const int32 Sec = int32(DiveTime);
	SetDisplay(TEXT("Clock"), FString::Printf(TEXT("%02d%02d%02d"), Sec / 3600, (Sec / 60) % 60, Sec % 60));

	// 指示灯：0 号红灯慢闪，6 号偶尔跳一下，其余常亮
	for (int32 i = 0; i < Lamps.Num(); ++i)
	{
		bool bOn = true;
		if (i == 0)
		{
			bOn = FMath::Fmod(T, 1.6f) < 0.8f;
		}
		else if (i == 6)
		{
			bOn = FMath::Fmod(T * 0.37f + 0.3f, 1.f) > 0.15f;
		}
		if (Lamps[i].IsValid())
		{
			Lamps[i]->SetScalarParameterValue(TEXT("emission_energy_multiplier"), bOn ? 3.f : 0.05f);
		}
	}
	for (int32 i = 0; i < Warns.Num(); ++i)
	{
		const bool bLit = WarnState[i] == 1 || (WarnState[i] == 2 && FMath::Fmod(T, 1.f) < 0.55f);
		if (Warns[i].IsValid())
		{
			Warns[i]->SetScalarParameterValue(TEXT("emission_energy_multiplier"), bLit ? 2.2f : 0.02f);
		}
	}
	// 流量计浮子：在刻度 4 附近轻轻上下抖（沿自己的局部 y，Godot 坐标；UE 里是 z）
	for (FFloat& F : Floats)
	{
		if (USceneComponent* N = F.Node.Get())
		{
			const float H = 0.044f + FMath::Sin(T * 2.3f + F.Phase) * 0.0015f + (FMath::FRand() - 0.5f) * 0.0006f;
			const FVector Up = N->GetRelativeRotation().RotateVector(FVector(0.f, 0.f, 1.f));
			N->SetRelativeLocation(F.Base + Up * H * 100.f);
		}
	}
}
