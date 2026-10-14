#include "Crew/CrewCharacter.h"

#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SpotLightComponent.h"
#include "Engine/SpotLight.h"
#include "EngineUtils.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Submarine/Submarine.h"

namespace
{
	constexpr float EyeOffset = 74.f;  // 相机在胶囊中心上方多少（眼睛离地 1.62 米）

	/** Godot 的视线（-Z 绕 Y 转 yaw、再抬 pitch）→ UE 局部方向（x 不变，y、z 对调） */
	FVector GodotDir(float YawDeg, float PitchDeg)
	{
		const float Y = FMath::DegreesToRadians(YawDeg);
		const float P = FMath::DegreesToRadians(PitchDeg);
		const FVector G(-FMath::Sin(Y) * FMath::Cos(P), FMath::Sin(P), -FMath::Cos(Y) * FMath::Cos(P));
		return FVector(G.X, G.Z, G.Y);
	}
}

ACrewCharacter::ACrewCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	// 舱里过道窄（Godot 版两个人错得开身，门洞一次过一个）：胶囊半径 22 厘米，身高 1.76 米
	GetCapsuleComponent()->InitCapsuleSize(22.f, 88.f);
	bUseControllerRotationYaw = true;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(GetCapsuleComponent());
	Camera->SetRelativeLocation(FVector(0.f, 0.f, EyeOffset));
	Camera->bUsePawnControlRotation = true;
	// Godot 版是竖直视角 72°；UE 的视角按水平算，16:9 下大约 104°
	Camera->SetFieldOfView(104.f);

	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->MaxWalkSpeed = WalkSpeed;
	Move->BrakingDecelerationWalking = 900.f;
	Move->GroundFriction = 10.f;
	// 舱里有台阶、格栅、门槛
	Move->MaxStepHeight = 30.f;
	Move->SetWalkableFloorAngle(50.f);
	// 站在开着的潜艇上：跟着艇走、跟着艇转
	Move->bImpartBaseVelocityX = true;
	Move->bImpartBaseVelocityY = true;
	Move->bImpartBaseVelocityZ = true;
	Move->bIgnoreBaseRotation = false;
}

ASubmarine* ACrewCharacter::FindSub()
{
	if (!Sub.IsValid())
	{
		for (TActorIterator<ASubmarine> It(GetWorld()); It; ++It)
		{
			Sub = *It;
		}
	}
	return Sub.Get();
}

void ACrewCharacter::BeginPlay()
{
	Super::BeginPlay();
	if (bStartSeated && FindSub())
	{
		Sit();
	}
}

void ACrewCharacter::BuildInput()
{
	if (Mapping)
	{
		return;
	}
	Mapping = NewObject<UInputMappingContext>(this, TEXT("CrewMapping"));
	auto MakeAction = [this](const TCHAR* Name, EInputActionValueType Type)
	{
		UInputAction* A = NewObject<UInputAction>(this, Name);
		A->ValueType = Type;
		return A;
	};
	MoveAction = MakeAction(TEXT("Move"), EInputActionValueType::Axis2D);
	LookAction = MakeAction(TEXT("Look"), EInputActionValueType::Axis2D);
	RunAction = MakeAction(TEXT("Run"), EInputActionValueType::Boolean);
	LiftAction = MakeAction(TEXT("Lift"), EInputActionValueType::Axis1D);
	InteractAction = MakeAction(TEXT("Interact"), EInputActionValueType::Boolean);
	ViewAction = MakeAction(TEXT("ToggleView"), EInputActionValueType::Boolean);
	LightsAction = MakeAction(TEXT("ToggleLights"), EInputActionValueType::Boolean);
	SonarAction = MakeAction(TEXT("ToggleSonar"), EInputActionValueType::Boolean);
	OrbitDragAction = MakeAction(TEXT("OrbitDrag"), EInputActionValueType::Boolean);
	ZoomAction = MakeAction(TEXT("Zoom"), EInputActionValueType::Axis1D);

	// WASD → 二维移动（X 前后，Y 左右）
	auto Map = [this](UInputAction* Action, FKey Key, bool bSwizzle, bool bNegate)
	{
		FEnhancedActionKeyMapping& M = Mapping->MapKey(Action, Key);
		if (bSwizzle)
		{
			M.Modifiers.Add(NewObject<UInputModifierSwizzleAxis>(this));
		}
		if (bNegate)
		{
			M.Modifiers.Add(NewObject<UInputModifierNegate>(this));
		}
	};
	Map(MoveAction, EKeys::W, true, false);
	Map(MoveAction, EKeys::S, true, true);
	Map(MoveAction, EKeys::D, false, false);
	Map(MoveAction, EKeys::A, false, true);
	Map(LiftAction, EKeys::SpaceBar, false, false);
	Map(LiftAction, EKeys::LeftControl, false, true);
	Mapping->MapKey(LookAction, EKeys::Mouse2D);
	Mapping->MapKey(RunAction, EKeys::LeftShift);
	Mapping->MapKey(InteractAction, EKeys::E);
	Mapping->MapKey(ViewAction, EKeys::Tab);
	Mapping->MapKey(LightsAction, EKeys::F);
	Mapping->MapKey(SonarAction, EKeys::Q);
	Mapping->MapKey(OrbitDragAction, EKeys::LeftMouseButton);
	Mapping->MapKey(ZoomAction, EKeys::MouseWheelAxis);
}

void ACrewCharacter::PawnClientRestart()
{
	Super::PawnClientRestart();
	BuildInput();
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (ULocalPlayer* LP = PC->GetLocalPlayer())
		{
			if (UEnhancedInputLocalPlayerSubsystem* Subsys = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
			{
				Subsys->AddMappingContext(Mapping, 0);
			}
		}
	}
}

void ACrewCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	BuildInput();
	if (UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(PlayerInputComponent))
	{
		Input->BindAction(MoveAction, ETriggerEvent::Triggered, this, &ACrewCharacter::Move);
		Input->BindAction(MoveAction, ETriggerEvent::Completed, this, &ACrewCharacter::MoveStop);
		Input->BindAction(LookAction, ETriggerEvent::Triggered, this, &ACrewCharacter::Look);
		Input->BindAction(LiftAction, ETriggerEvent::Triggered, this, &ACrewCharacter::Lift);
		Input->BindAction(LiftAction, ETriggerEvent::Completed, this, &ACrewCharacter::LiftStop);
		Input->BindAction(RunAction, ETriggerEvent::Started, this, &ACrewCharacter::RunStart);
		Input->BindAction(RunAction, ETriggerEvent::Completed, this, &ACrewCharacter::RunStop);
		Input->BindAction(InteractAction, ETriggerEvent::Started, this, &ACrewCharacter::Interact);
		Input->BindAction(ViewAction, ETriggerEvent::Started, this, &ACrewCharacter::ToggleView);
		Input->BindAction(LightsAction, ETriggerEvent::Started, this, &ACrewCharacter::ToggleLights);
		Input->BindAction(SonarAction, ETriggerEvent::Started, this, &ACrewCharacter::ToggleSonar);
		Input->BindAction(OrbitDragAction, ETriggerEvent::Started, this, &ACrewCharacter::OrbitDragStart);
		Input->BindAction(OrbitDragAction, ETriggerEvent::Completed, this, &ACrewCharacter::OrbitDragStop);
		Input->BindAction(ZoomAction, ETriggerEvent::Triggered, this, &ACrewCharacter::Zoom);
	}
}

void ACrewCharacter::Move(const FInputActionValue& Value)
{
	MoveInput = Value.Get<FVector2D>();
	if (bSeated || bExternal)
	{
		return;  // 坐着时 WASD 开船（Tick 里交给潜艇）
	}
	const FRotator Yaw(0.f, GetControlRotation().Yaw, 0.f);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), MoveInput.X);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), MoveInput.Y);
}

void ACrewCharacter::MoveStop(const FInputActionValue& Value)
{
	MoveInput = FVector2D::ZeroVector;
}

void ACrewCharacter::Look(const FInputActionValue& Value)
{
	const FVector2D V = Value.Get<FVector2D>();
	if (bExternal)
	{
		// 舱外：鼠标环绕艇身（Godot 版拖动左键；鼠标被游戏捕获时直接转）
		OrbitYaw -= V.X * 0.25f;
		OrbitPitch = FMath::Clamp(OrbitPitch + V.Y * 0.25f, -80.f, 60.f);
		return;
	}
	if (bSeated)
	{
		SeatYaw = FMath::Clamp(SeatYaw - V.X * LookSensitivity, -110.f, 110.f);
		SeatPitch = FMath::Clamp(SeatPitch + V.Y * LookSensitivity, -70.f, 60.f);
		return;
	}
	AddControllerYawInput(V.X * LookSensitivity);
	AddControllerPitchInput(-V.Y * LookSensitivity);
}

void ACrewCharacter::Lift(const FInputActionValue& Value)
{
	LiftInput = Value.Get<float>();
}

void ACrewCharacter::LiftStop(const FInputActionValue& Value)
{
	LiftInput = 0.f;
}

void ACrewCharacter::RunStart()
{
	GetCharacterMovement()->MaxWalkSpeed = RunSpeed;
}

void ACrewCharacter::RunStop()
{
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
}

void ACrewCharacter::Interact()
{
	ASubmarine* S = FindSub();
	if (!S || bExternal)
	{
		return;
	}
	if (bSeated)
	{
		Stand();
		return;
	}
	// 走到驾驶椅跟前（眼睛离坐姿的眼睛位置一米二以内）就坐下；开门以后搬
	if (USceneComponent* Eye = S->FindNode(TEXT("Anchor_Eye")))
	{
		if (FVector::Dist(Camera->GetComponentLocation(), Eye->GetComponentLocation()) < 120.f)
		{
			Sit();
		}
	}
}

void ACrewCharacter::Sit()
{
	bSeated = true;
	SeatYaw = 0.f;
	SeatPitch = 0.f;
	GetCharacterMovement()->SetMovementMode(MOVE_None);
	SetActorEnableCollision(false);
	UpdateSeat();
}

void ACrewCharacter::Stand()
{
	ASubmarine* S = FindSub();
	USceneComponent* StandAnchor = S ? S->FindNode(TEXT("Anchor_Stand")) : nullptr;
	bSeated = false;
	if (S)
	{
		S->SetSteering(FVector::ZeroVector);
	}
	if (StandAnchor)
	{
		SetActorLocation(StandAnchor->GetComponentLocation() + FVector(0.f, 0.f, 92.f));
	}
	SetActorEnableCollision(true);
	GetCharacterMovement()->SetMovementMode(MOVE_Walking);
	if (AController* C = GetController())
	{
		C->SetControlRotation(FRotator(0.f, S ? S->GetActorRotation().Yaw : GetActorRotation().Yaw, 0.f));
	}
}

void ACrewCharacter::UpdateSeat()
{
	ASubmarine* S = FindSub();
	USceneComponent* Eye = S ? S->FindNode(TEXT("Anchor_Eye")) : nullptr;
	if (!Eye)
	{
		return;
	}
	FTransform T = Eye->GetComponentTransform();
	T.SetScale3D(FVector::OneVector);
	const FVector Dir = T.TransformVectorNoScale(GodotDir(SeatYaw, SeatPitch));
	SetActorLocation(T.GetLocation() - FVector(0.f, 0.f, EyeOffset));
	if (AController* C = GetController())
	{
		C->SetControlRotation(Dir.Rotation());
	}
}

void ACrewCharacter::ToggleView()
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	ASubmarine* S = FindSub();
	if (!PC || !S)
	{
		return;
	}
	bExternal = !bExternal;
	if (bExternal)
	{
		if (!ExternalCamera)
		{
			ExternalCamera = GetWorld()->SpawnActor<ACameraActor>();
			ExternalCamera->GetCameraComponent()->SetConstraintAspectRatio(false);
			// Godot 版舱外相机竖直视角 60°
			ExternalCamera->GetCameraComponent()->SetFieldOfView(90.f);
			ExternalFill = GetWorld()->SpawnActor<ASpotLight>();
			USpotLightComponent* L = ExternalFill->SpotLightComponent;
			L->SetMobility(EComponentMobility::Movable);
			L->SetIntensityUnits(ELightUnits::Candelas);
			L->SetLightColor(FLinearColor(FColor(230, 242, 255)));
			L->SetCastShadows(true);
			L->SetSourceRadius(20.f);
		}
		UpdateExternal();
		PC->SetViewTarget(ExternalCamera);
	}
	else
	{
		PC->SetViewTarget(this);
	}
	if (ExternalFill)
	{
		ExternalFill->SetActorHiddenInGame(!bExternal);
	}
}

void ACrewCharacter::UpdateExternal()
{
	ASubmarine* S = FindSub();
	if (!S || !ExternalCamera)
	{
		return;
	}
	// 环绕中心在艇身中部（Godot 的艇身局部 (0, 0.6, 3.6) 米），相机在 center + rot·(0, 0, distance)（Godot 版 external_camera.gd）
	const FTransform BodyT(S->GetBody()->GetComponentQuat(), S->GetBody()->GetComponentLocation());
	const FVector Center = BodyT.TransformPosition(FVector(0.f, 360.f, 60.f));
	const float Ph = FMath::DegreesToRadians(OrbitYaw - S->HeadingDeg());
	const float Th = FMath::DegreesToRadians(OrbitPitch);
	const float D = OrbitDist;
	const FVector G(D * FMath::Cos(Th) * FMath::Sin(Ph), -D * FMath::Sin(Th), D * FMath::Cos(Th) * FMath::Cos(Ph));
	const FVector Loc = Center + FVector(G.X, G.Z, G.Y) * 100.f;
	const FRotator Rot = (Center - Loc).Rotation();
	ExternalCamera->SetActorLocationAndRotation(Loc, Rot);
	// 补光灯在相机斜上方一点，对着艇身；亮度、光束宽度跟着距离走
	USpotLightComponent* L = ExternalFill->SpotLightComponent;
	const FRotationMatrix RM(Rot);
	const FVector Lamp = Loc + RM.GetUnitAxis(EAxis::Z) * 200.f + RM.GetUnitAxis(EAxis::Y) * 150.f;
	ExternalFill->SetActorLocationAndRotation(Lamp, (Center - Lamp).Rotation());
	const float Angle = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan(9.f / D)), 14.f, 55.f);
	L->SetOuterConeAngle(Angle);
	L->SetInnerConeAngle(Angle * 0.5f);
	L->SetAttenuationRadius((D + 12.f) * 100.f);
	L->SetIntensity(0.3f * D * D * S->FloodlightScale);
	L->SetVolumetricScatteringIntensity(FMath::Min(1.f, 150.f / (D * D)));
}

void ACrewCharacter::Zoom(const FInputActionValue& Value)
{
	if (bExternal)
	{
		const float W = Value.Get<float>();
		OrbitDist = FMath::Clamp(OrbitDist * (W > 0.f ? 0.9f : 1.1f), 6.f, 36.f);
	}
}

void ACrewCharacter::ToggleLights()
{
	if (ASubmarine* S = FindSub())
	{
		S->SetLights(!S->AreLightsOn());
	}
}

void ACrewCharacter::ToggleSonar()
{
	if (ASubmarine* S = FindSub())
	{
		S->SetSonarActive(!S->IsSonarActive());
	}
}

void ACrewCharacter::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	ASubmarine* S = FindSub();
	if (!S)
	{
		return;
	}
	// 坐在驾驶椅上（单机时舱外视角也能开，看艇怎么动）：WASD 推进 / 转向，空格 / Ctrl 升降
	if (bSeated || bExternal)
	{
		S->SetSteering(FVector(MoveInput.X, LiftInput, -MoveInput.Y));
	}
	if (bSeated)
	{
		UpdateSeat();
	}
	if (bExternal)
	{
		UpdateExternal();
	}
}
