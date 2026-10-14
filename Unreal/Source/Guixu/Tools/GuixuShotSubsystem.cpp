#include "Tools/GuixuShotSubsystem.h"

#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/SpotLightComponent.h"
#include "Engine/SpotLight.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Submarine/Submarine.h"
#include "UnrealClient.h"

namespace
{
	constexpr float DeckY = -0.9f;     // Godot 版舱里甲板高度（艇身局部坐标，米）
	constexpr float EyeHeight = 1.62f;

	/** Godot 的视线（-Z 绕 Y 转 yaw、再抬 pitch）→ UE 局部方向（x 不变，y、z 对调） */
	FVector GodotDir(float YawDeg, float PitchDeg)
	{
		const float Y = FMath::DegreesToRadians(YawDeg);
		const float P = FMath::DegreesToRadians(PitchDeg);
		const FVector G(-FMath::Sin(Y) * FMath::Cos(P), FMath::Sin(P), -FMath::Cos(Y) * FMath::Cos(P));
		return FVector(G.X, G.Z, G.Y);
	}
}

bool UGuixuShotSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	FString Path;
	return FParse::Value(FCommandLine::Get(), TEXT("-GuixuShotJob="), Path);
}

void UGuixuShotSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	if (!FParse::Value(FCommandLine::Get(), TEXT("-GuixuShotJob="), JobPath))
	{
		return;
	}
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *JobPath))
	{
		UE_LOGF(LogTemp, Error, "[shot] 读不到任务文件 %ls", *JobPath);
		return;
	}
	TSharedPtr<FJsonObject> Root;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		UE_LOGF(LogTemp, Error, "[shot] 任务文件不是 JSON：%ls", *JobPath);
		return;
	}
	OutDir = Root->GetStringField(TEXT("out_dir"));
	Root->TryGetNumberField(TEXT("fov_v"), FovV);
	Root->TryGetNumberField(TEXT("warm_frames"), WarmFrames);
	Root->TryGetNumberField(TEXT("settle_frames"), SettleFrames);
	for (const TSharedPtr<FJsonValue>& V : Root->GetArrayField(TEXT("views")))
	{
		const TSharedPtr<FJsonObject>& O = V->AsObject();
		FView View;
		View.Name = O->GetStringField(TEXT("name"));
		const TArray<TSharedPtr<FJsonValue>>* Arr;
		if (O->TryGetArrayField(TEXT("at"), Arr) && Arr->Num() == 2)
		{
			View.bHasAt = true;
			View.At = FVector2D((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber());
		}
		if (O->TryGetArrayField(TEXT("loc"), Arr) && Arr->Num() == 3)
		{
			View.bHasLoc = true;
			View.Loc = FVector((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber(), (*Arr)[2]->AsNumber());
		}
		if (O->TryGetArrayField(TEXT("rot"), Arr) && Arr->Num() == 3)
		{
			View.Rot = FRotator((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber(), (*Arr)[2]->AsNumber());
		}
		O->TryGetStringField(TEXT("node"), View.Node);
		if (O->TryGetNumberField(TEXT("orbit"), View.OrbitYaw))
		{
			View.bOrbit = true;
		}
		O->TryGetNumberField(TEXT("orbit_pitch"), View.OrbitPitch);
		O->TryGetNumberField(TEXT("orbit_dist"), View.OrbitDist);
		O->TryGetNumberField(TEXT("fov_v"), View.FovV);
		O->TryGetNumberField(TEXT("yaw"), View.Yaw);
		O->TryGetNumberField(TEXT("pitch"), View.Pitch);
		Views.Add(View);
	}
	IFileManager::Get().MakeDirectory(*OutDir, true);
	bActive = Views.Num() > 0;
	UE_LOGF(LogTemp, Display, "[shot] 任务 %ls：%d 个机位", *JobPath, Views.Num());
}

bool UGuixuShotSubsystem::PlaceCamera(const FView& View)
{
	UWorld* World = GetGameInstance()->GetWorld();
	APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	if (!PC)
	{
		return false;
	}
	ASubmarine* Sub = nullptr;
	for (TActorIterator<ASubmarine> It(World); It; ++It)
	{
		Sub = *It;
	}
	FVector Loc;
	FRotator Rot;
	if (Fill)
	{
		Fill->SetActorHiddenInGame(true);
	}
	if (View.bOrbit && Sub)
	{
		// 环绕中心在艇身中部（围壳和尾舵之间）：Godot 的艇身局部 (0, 0.6, 3.6) 米
		const FTransform BodyT(Sub->GetBody()->GetComponentQuat(), Sub->GetBody()->GetComponentLocation());
		const FVector Center = BodyT.TransformPosition(FVector(0.f, 360.f, 60.f));
		// Godot：rot = 欧拉(pitch, yaw + 艇的偏航)，相机在 center + rot·(0, 0, distance)。艇的偏航按艇首相对关卡 -Y 算
		const float SubYaw = -(Sub->HeadingDeg());
		const float Ph = FMath::DegreesToRadians(View.OrbitYaw + SubYaw);
		const float Th = FMath::DegreesToRadians(View.OrbitPitch);
		const float D = View.OrbitDist;
		const FVector G(D * FMath::Cos(Th) * FMath::Sin(Ph), -D * FMath::Sin(Th), D * FMath::Cos(Th) * FMath::Cos(Ph));
		Loc = Center + FVector(G.X, G.Z, G.Y) * 100.f;
		Rot = (Center - Loc).Rotation();
		// 补光灯：在相机斜上方一点（避免正面平光），对着艇身中部；亮度、光束宽度跟着距离走（Godot 版的算法）
		if (!Fill)
		{
			Fill = World->SpawnActor<ASpotLight>(Loc, Rot);
			USpotLightComponent* L = Fill->SpotLightComponent;
			L->SetMobility(EComponentMobility::Movable);
			L->SetIntensityUnits(ELightUnits::Candelas);
			L->SetLightColor(FLinearColor(FColor(230, 242, 255)));
			L->SetCastShadows(true);
			L->SetSourceRadius(20.f);
		}
		USpotLightComponent* L = Fill->SpotLightComponent;
		const FRotationMatrix RM(Rot);
		const FVector Lamp = Loc + RM.GetUnitAxis(EAxis::Z) * 200.f + RM.GetUnitAxis(EAxis::Y) * 150.f;
		Fill->SetActorLocationAndRotation(Lamp, (Center - Lamp).Rotation());
		const float Angle = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan(9.f / D)), 14.f, 55.f);
		L->SetOuterConeAngle(Angle);
		L->SetInnerConeAngle(Angle * 0.5f);
		L->SetAttenuationRadius((D + 12.f) * 100.f);
		L->SetIntensity(0.3f * D * D * Sub->FloodlightScale);
		L->SetVolumetricScatteringIntensity(FMath::Min(1.f, 150.f / (D * D)));
		Fill->SetActorHiddenInGame(false);
	}
	else if (View.bHasLoc)
	{
		Loc = View.Loc;
		Rot = View.Rot;
	}
	else
	{
		if (!Sub)
		{
			return false;
		}
		FTransform Basis;
		FVector Local = FVector::ZeroVector;
		if (!View.Node.IsEmpty())
		{
			USceneComponent* N = Sub->FindNode(FName(*View.Node));
			if (!N)
			{
				UE_LOGF(LogTemp, Error, "[shot] 潜艇上找不到节点 %ls", *View.Node);
				return false;
			}
			Basis = N->GetComponentTransform();
		}
		else
		{
			Basis = Sub->GetBody()->GetComponentTransform();
			Local = FVector(View.At.X * 100.f, View.At.Y * 100.f, (DeckY + EyeHeight) * 100.f);
		}
		Basis.SetScale3D(FVector::OneVector);
		Loc = Basis.TransformPosition(Local);
		Rot = FRotationMatrix::MakeFromX(Basis.TransformVectorNoScale(GodotDir(View.Yaw, View.Pitch))).Rotator();
	}
	if (!Camera)
	{
		Camera = World->SpawnActor<ACameraActor>(Loc, Rot);
		Camera->GetCameraComponent()->SetConstraintAspectRatio(false);
	}
	Camera->SetActorLocationAndRotation(Loc, Rot);
	FVector2D Size(16, 9);
	if (GEngine && GEngine->GameViewport)
	{
		GEngine->GameViewport->GetViewportSize(Size);
	}
	const float V = View.FovV > 0.f ? View.FovV : (View.bOrbit ? 60.f : FovV);
	const double HFov = FMath::RadiansToDegrees(2.0 * FMath::Atan(FMath::Tan(FMath::DegreesToRadians(V) * 0.5) * Size.X / FMath::Max(Size.Y, 1.0)));
	Camera->GetCameraComponent()->SetFieldOfView(HFov);
	PC->SetViewTarget(Camera);
	return true;
}

void UGuixuShotSubsystem::Tick(float DeltaTime)
{
	++Frame;
	if (Phase == 0)
	{
		// 等关卡、着色器、贴图、Lumen 的表面缓存都起来
		if (Frame >= WarmFrames && PlaceCamera(Views[Index]))
		{
			Phase = 1;
			Frame = 0;
		}
		return;
	}
	if (Phase == 1)
	{
		if (Frame >= SettleFrames)
		{
			const FString Path = FPaths::Combine(OutDir, Views[Index].Name + TEXT(".png"));
			FScreenshotRequest::RequestScreenshot(Path, false, false);
			Results.Add(Path);
			UE_LOGF(LogTemp, Display, "[shot] 截图 %ls", *Path);
			Phase = 2;
			Frame = 0;
		}
		return;
	}
	// 截图在下一帧写盘，多等几帧再换机位
	if (Frame >= 5)
	{
		++Index;
		if (Index >= Views.Num())
		{
			Finish();
			return;
		}
		PlaceCamera(Views[Index]);
		Phase = 1;
		Frame = 0;
	}
}

void UGuixuShotSubsystem::Finish()
{
	bActive = false;
	FString Json = TEXT("{\"results\": [");
	for (int32 i = 0; i < Results.Num(); ++i)
	{
		Json += FString::Printf(TEXT("%s\"%s\""), i ? TEXT(", ") : TEXT(""), *Results[i].Replace(TEXT("\\"), TEXT("/")));
	}
	Json += TEXT("]}");
	FFileHelper::SaveStringToFile(Json, *(JobPath + TEXT(".done.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	UE_LOGF(LogTemp, Display, "[shot] 全部截完");
	FPlatformMisc::RequestExit(false, TEXT("GuixuShot"));
}
