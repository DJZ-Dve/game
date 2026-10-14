#include "Submarine/Submarine.h"

#include "Components/DecalComponent.h"
#include "Components/PointLightComponent.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"
#include "Materials/MaterialInterface.h"
#include "Submarine/Instruments.h"
#include "Submarine/Sonar.h"
#include "Components/SpotLightComponent.h"

namespace
{
	// Godot 色值是 sRGB
	FLinearColor GodotColor(float R, float G, float B) { return FLinearColor(FColor(FMath::RoundToInt(R * 255), FMath::RoundToInt(G * 255), FMath::RoundToInt(B * 255))); }

	/** 舱内灯（Godot 版 cockpit_props.gd 的 LIGHTS）：挂点名前缀 → 参数。能量是 Godot 的单位，射程是米 */
	struct FCabinLightDef
	{
		const TCHAR* Prefix;
		bool bSpot;
		FLinearColor Color;
		float Energy;
		float Range;
		float Angle;       // 聚光灯半角（度）
		bool bShadow;
		float Fog;         // 体积雾里的光锥强度
		float Size;        // 光源半径（米）：Godot 版灯是 3 厘米再加阴影模糊 1.5，UE 的软阴影靠光源大小，顶灯放大到 8 厘米
	};

	const FCabinLightDef CabinLights[] = {
		// 顶灯：笼罩里的白炽灯泡，暖白，带阴影——舱里主要的光，故意只有三盏，中间留出暗区；舱里有薄水汽，顶灯下面看得到光锥
		{TEXT("CabinLight_Dome"), false, GodotColor(1.0f, 0.8f, 0.58f), 1.5f, 3.4f, 0.f, true, 1.2f, 0.08f},
		// 后隔壁上的灯
		{TEXT("CabinLight_Aft"), false, GodotColor(1.0f, 0.8f, 0.58f), 0.9f, 2.8f, 0.f, true, 0.8f, 0.08f},
		// 工作台灯罩下的日光灯管：偏冷，照亮仪表板和桌面（Godot 版用投影贴图把光斑拉成长条，这里先用源长度）
		{TEXT("CabinLight_Strip"), true, GodotColor(0.82f, 0.95f, 0.88f), 0.9f, 1.7f, 70.f, true, 0.f, 0.03f},
		// 舱底的防水灯：昏黄，从格栅缝里往上漏
		{TEXT("CabinLight_Bilge"), false, GodotColor(1.0f, 0.48f, 0.16f), 0.3f, 1.9f, 0.f, true, 0.f, 0.05f},
		// 红色夜灯
		{TEXT("CabinLight_Night"), false, GodotColor(1.0f, 0.12f, 0.06f), 0.3f, 2.2f, 0.f, false, 0.f, 0.03f},
		// 主控台蛇管台灯
		{TEXT("CabinSpot_Console"), true, GodotColor(1.0f, 0.86f, 0.66f), 1.0f, 1.5f, 50.f, true, 0.f, 0.03f},
		// 生活舱：床头小灯、厨房吊柜下的灯管
		{TEXT("CabinLight_Bunk"), false, GodotColor(1.0f, 0.7f, 0.42f), 0.45f, 1.3f, 0.f, true, 0.f, 0.03f},
		{TEXT("CabinLight_Galley"), true, GodotColor(0.85f, 0.95f, 0.88f), 0.8f, 1.4f, 65.f, true, 0.f, 0.03f},
	};

	/** 个别灯的能量（Godot 版 LIGHT_OVERRIDES）：生活舱铺位上方那盏顶灯坏了只剩一点光；闪烁以后搬 */
	float EnergyOverride(const FString& Name, float Energy)
	{
		if (Name == TEXT("CabinLight_Dome_5")) return 0.35f;
		if (Name == TEXT("CabinLight_Bunk_L0")) return 0.3f;
		return Energy;
	}
}

namespace
{
	/** Poly Haven 道具（Godot 版 cockpit_props.gd 的 PROPS）：挂点 → 素材、缩放、绕竖轴转、抬高、躺倒 / 侧放、只留哪些节点、去掉哪些节点、子节点额外转 */
	struct FPropDef
	{
		FString Anchor;
		FString Asset;
		float Scale = 1.f;
		float Rot = 0.f;       // Godot rotation_degrees.y
		float Lift = 0.f;      // 米
		float TiltX = 0.f;     // Godot rotation_degrees.x（lay = -90）
		TSet<FName> Keep;
		TSet<FName> Drop;
		TMap<FName, float> NodeYaw;  // 子节点 rotation_degrees.y 加多少
	};

	const TArray<FPropDef>& PropDefs()
	{
		static TArray<FPropDef> Defs;
		if (Defs.Num())
		{
			return Defs;
		}
		auto Add = [](const TCHAR* Anchor, const TCHAR* Asset) -> FPropDef&
		{
			FPropDef& D = Defs.AddDefaulted_GetRef();
			D.Anchor = Anchor;
			D.Asset = Asset;
			return D;
		};
		{ FPropDef& D = Add(TEXT("Anchor_ShrineLamp"), TEXT("brass_diya_lantern")); D.Scale = 0.45f; D.Keep.Add(TEXT("brass_diya_lantern")); D.Lift = 0.027f; }
		{ FPropDef& D = Add(TEXT("Anchor_Radio"), TEXT("vintage_radio_transceiver"));
			D.Drop = {TEXT("vintage_radio_transceiver_antenna"), TEXT("vintage_radio_transceiver_antenna_plug_a"), TEXT("vintage_radio_transceiver_antenna_plug_b")}; }
		{ FPropDef& D = Add(TEXT("Anchor_PowerBox"), TEXT("power_box_01")); D.NodeYaw.Add(TEXT("power_box_01_door"), -112.f); }
		{ FPropDef& D = Add(TEXT("Anchor_Scope"), TEXT("vintage_spacecraft_instrument")); D.Lift = 0.135f; }
		Add(TEXT("Anchor_GasMask"), TEXT("old_gas_mask"));
		{ FPropDef& D = Add(TEXT("Anchor_Extinguisher"), TEXT("korean_fire_extinguisher_01")); D.Scale = 0.85f; }
		Add(TEXT("Anchor_Thermos"), TEXT("plastic_thermos"));
		{ FPropDef& D = Add(TEXT("Anchor_Checklist"), TEXT("clipboard")); D.TiltX = 90.f; }
		{ FPropDef& D = Add(TEXT("Anchor_Logbook"), TEXT("binder_notebook")); D.Keep.Add(TEXT("binder_notebook_closed")); }
		{ FPropDef& D = Add(TEXT("Anchor_Flashlight"), TEXT("signal_flashlight")); D.TiltX = -90.f; D.Lift = 0.022f; }
		Add(TEXT("Anchor_Multimeter"), TEXT("retro_multimeter"));
		Add(TEXT("Anchor_Medical"), TEXT("medical_box"));
		{ FPropDef& D = Add(TEXT("Anchor_Walkman"), TEXT("portable_cassette_player")); D.TiltX = -90.f; D.Lift = 0.017f; }
		Add(TEXT("Anchor_Spectacles"), TEXT("round_spectacles"));
		Add(TEXT("Anchor_Watch"), TEXT("digital_wrist_watch"));
		{ FPropDef& D = Add(TEXT("Anchor_Screwdriver"), TEXT("screwdriver")); D.TiltX = -90.f; D.Lift = 0.0135f; }
		{ FPropDef& D = Add(TEXT("Anchor_Pliers"), TEXT("pliers")); D.TiltX = -90.f; D.Lift = 0.009f; }
		Add(TEXT("Anchor_Tape"), TEXT("medical_tape"));
		// 生活舱
		Add(TEXT("Anchor_GalleyThermos"), TEXT("modified_thermos"));
		{ FPropDef& D = Add(TEXT("Anchor_Notepads"), TEXT("office_notepads")); D.Keep.Add(TEXT("office_notepads_yellow_pad")); }
		Add(TEXT("Anchor_PocketWatch"), TEXT("pocket_watch"));
		{ FPropDef& D = Add(TEXT("Anchor_BunkBook"), TEXT("binder_notebook")); D.Keep.Add(TEXT("binder_notebook_closed")); }
		Add(TEXT("Anchor_BunkSpectacles"), TEXT("round_spectacles"));
		Add(TEXT("Anchor_Wrench"), TEXT("adjustable_wrench"));
		Add(TEXT("Anchor_Compass"), TEXT("seadogs_compass"));
		return Defs;
	}

	/** Godot 的旋转（右手系）换到 UE（坐标 y、z 对调，是个镜像）：绕对调后的轴转相反的角度 */
	FQuat GodotAxisAngle(const FVector& GodotAxis, float Degrees)
	{
		return FQuat(FVector(GodotAxis.X, GodotAxis.Z, GodotAxis.Y), FMath::DegreesToRadians(-Degrees));
	}
}

ASubmarine::ASubmarine()
{
	PrimaryActorTick.bCanEverTick = true;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;
	Body = CreateDefaultSubobject<USceneComponent>(TEXT("Body"));
	Body->SetupAttachment(Root);
	// glTF 的 -Z（艇首）在 UE 里是 -Y，转 90° 到 +X
	Body->SetRelativeRotation(FRotator(0.f, 90.f, 0.f));
	Instruments = CreateDefaultSubobject<UInstrumentsComponent>(TEXT("Instruments"));
	Sonar = CreateDefaultSubobject<USonarComponent>(TEXT("Sonar"));
}

float ASubmarine::HeadingDeg() const
{
	return FMath::Fmod(GetActorRotation().Yaw + 90.f + 720.f, 360.f);
}

float ASubmarine::Altitude() const
{
	const UWorld* World = GetWorld();
	if (!World)
	{
		return -1.f;
	}
	const FVector Origin = GetActorLocation() - FVector(0.f, 0.f, 120.f);
	FHitResult Hit;
	FCollisionQueryParams Params(TEXT("SubAltitude"), false, this);
	if (World->LineTraceSingleByChannel(Hit, Origin, Origin - FVector(0.f, 0.f, 9900.f), ECC_WorldStatic, Params))
	{
		return Hit.Distance / 100.f;
	}
	return -1.f;
}

void ASubmarine::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	Floodlights.Reset();
	Exterior = UGuixuSceneLibrary::Build(this, Body, ExteriorScene, TEXT("Ext_"));
	Cockpit = UGuixuSceneLibrary::Build(this, Body, CockpitScene, TEXT("Cab_"));
	BuildCabinLights();
	BuildFloodlights();
	BuildDecals();
	BuildProps();
	BuildStern();
	Instruments->Setup(this);
	Sonar->Setup(this);
}

USceneComponent* ASubmarine::FindNode(FName Name) const
{
	if (USceneComponent* C = Cockpit.Find(Name))
	{
		return C;
	}
	return Exterior.Find(Name);
}

void ASubmarine::BuildCabinLights()
{
	for (const auto& It : Cockpit.ByName)
	{
		const FString Name = It.Key.ToString();
		const FCabinLightDef* Def = nullptr;
		for (const FCabinLightDef& D : CabinLights)
		{
			if (Name.StartsWith(D.Prefix))
			{
				Def = &D;
			}
		}
		if (!Def)
		{
			continue;
		}
		const float Energy = EnergyOverride(Name, Def->Energy);
		ULocalLightComponent* Light;
		if (Def->bSpot)
		{
			USpotLightComponent* S = UGuixuSceneLibrary::AddComponent<USpotLightComponent>(this, It.Value, FName(*(Name + TEXT("_Light"))));
			S->SetOuterConeAngle(Def->Angle);
			S->SetInnerConeAngle(Def->Angle * 0.4f);
			// Godot 的聚光灯朝自己的 -Z；换到 UE 是 -Y，UE 的聚光灯朝 +X：转 -90°
			S->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
			Light = S;
		}
		else
		{
			Light = UGuixuSceneLibrary::AddComponent<UPointLightComponent>(this, It.Value, FName(*(Name + TEXT("_Light"))));
		}
		Light->SetMobility(EComponentMobility::Movable);
		Light->SetIntensityUnits(ELightUnits::Candelas);
		Light->SetIntensity(Energy * CabinLightScale);
		Light->SetLightColor(Def->Color);
		Light->SetAttenuationRadius(Def->Range * 100.f);
		Light->SetCastShadows(Def->bShadow);
		Light->SetVolumetricScatteringIntensity(Def->Fog);
		if (UPointLightComponent* P = Cast<UPointLightComponent>(Light))
		{
			P->SetSourceRadius(Def->Size * 100.f);
		}
	}
}

void ASubmarine::BuildFloodlights()
{
	for (USceneComponent* Anchor : Exterior.FindPrefix(TEXT("Light_")))
	{
		const FString Name = Anchor->GetName();
		USpotLightComponent* S = UGuixuSceneLibrary::AddComponent<USpotLightComponent>(this, Anchor, FName(*(Name + TEXT("_Spot"))));
		S->SetMobility(EComponentMobility::Movable);
		S->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
		S->SetIntensityUnits(ELightUnits::Candelas);
		// 侧面两盏暗一点（Godot 版 Light_S*）
		const bool bSide = Name.Contains(TEXT("Light_S"));
		S->SetIntensity(FloodlightEnergy * (bSide ? 0.8f : 1.0f) * FloodlightScale);
		S->SetLightColor(FloodlightColor);
		S->SetAttenuationRadius(FloodlightRange * 100.f);
		S->SetOuterConeAngle(FloodlightAngle);
		S->SetInnerConeAngle(FloodlightAngle * 0.55f);
		S->SetSourceRadius(12.f);
		S->SetCastShadows(true);
		// Godot 版体积雾能量是 4；UE 的灯近处按距离平方变得很亮，光锥根部会糊成一片白，压低
		S->SetVolumetricScatteringIntensity(1.2f);
		S->SetVisibility(bFloodlightsOn);
		Floodlights.Add(S);
	}
}

void ASubmarine::BuildDecals()
{
	// 驾驶舱模型里的 Decal_<种类>_NN 挂点（Godot 版 cockpit_props.gd 的 _add_decals）：贴花投射盒就是挂点的单位立方体乘挂点缩放，
	// 沿挂点的 -y（Godot 坐标）往下投，贴图 U 沿 x、V 沿 z。材质实例由 Scripts/build_materials.py 建（/Game/Decals/MI_Decal_<种类>）
	TMap<FString, UMaterialInterface*> Cache;
	for (const auto& It : Cockpit.ByName)
	{
		const FString Name = It.Key.ToString();
		if (!Name.StartsWith(TEXT("Decal_")))
		{
			continue;
		}
		TArray<FString> Parts;
		Name.ParseIntoArray(Parts, TEXT("_"));
		if (Parts.Num() < 2)
		{
			continue;
		}
		UMaterialInterface*& Mat = Cache.FindOrAdd(Parts[1]);
		if (!Mat)
		{
			Mat = LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/Decals/MI_Decal_%s.MI_Decal_%s"), *Parts[1], *Parts[1]));
		}
		if (!Mat)
		{
			UE_LOGF(LogTemp, Warning, "未知贴花 %ls", *Name);
			continue;
		}
		USceneComponent* Anchor = It.Value;
		const FVector S = Anchor->GetComponentScale();
		UDecalComponent* D = UGuixuSceneLibrary::AddComponent<UDecalComponent>(this, Anchor, FName(*(Name + TEXT("_Decal"))));
		D->SetDecalMaterial(Mat);
		// 挂点带不等比缩放，贴花的轴跟挂点的轴不重合，缩放不能继承：用世界缩放 1，尺寸直接算到 DecalSize（半边长，厘米）里
		D->SetUsingAbsoluteScale(true);
		D->SetWorldScale3D(FVector::OneVector);
		// 贴花的 X（投射方向）= 挂点的 Z（Godot 的 y），Z（贴图 U）= 挂点的 X，Y = 挂点的 -Y（贴图 V 沿 -Y，也就是挂点的 +Y、Godot 的 z）
		D->SetRelativeRotation(FRotationMatrix::MakeFromXZ(FVector(0.f, 0.f, 1.f), FVector(1.f, 0.f, 0.f)).Rotator());
		D->DecalSize = FVector(50.f * S.Z, 50.f * S.Y, 50.f * S.X);
		D->MarkRenderStateDirty();
	}
}

void ASubmarine::BuildProps()
{
	for (const FPropDef& P : PropDefs())
	{
		USceneComponent* Anchor = Cockpit.Find(FName(*P.Anchor));
		if (!Anchor)
		{
			continue;
		}
		const UGuixuSceneAsset* Asset = LoadObject<UGuixuSceneAsset>(nullptr, *FString::Printf(TEXT("/Game/Props/%s/SA_%s.SA_%s"), *P.Asset, *P.Asset, *P.Asset));
		if (!Asset || Asset->Nodes.Num() == 0)
		{
			UE_LOGF(LogTemp, Warning, "道具还没导入：%ls（Scripts/import_all.py props）", *P.Asset);
			continue;
		}
		USceneComponent* PropRoot = UGuixuSceneLibrary::AddComponent<USceneComponent>(this, Anchor, FName(*(P.Anchor + TEXT("_Prop"))));
		// Godot 的欧拉角顺序是 YXZ：先绕 X（躺倒 / 侧放），再绕 Y（转向）
		const FQuat Q = GodotAxisAngle(FVector(0, 1, 0), P.Rot) * GodotAxisAngle(FVector(1, 0, 0), P.TiltX);
		PropRoot->SetRelativeTransform(FTransform(Q, FVector(0.f, 0.f, P.Lift * 100.f), FVector(P.Scale)));
		const FGuixuSceneInstance Inst = UGuixuSceneLibrary::Build(this, PropRoot, Asset, P.Anchor + TEXT("_"),
			P.Keep.Num() ? &P.Keep : nullptr, P.Drop.Num() ? &P.Drop : nullptr);
		for (const auto& It : P.NodeYaw)
		{
			if (USceneComponent* C = Inst.Find(It.Key))
			{
				C->AddLocalRotation(GodotAxisAngle(FVector(0, 1, 0), It.Value));
			}
		}
	}
}

// ---------------------------------------------------------------------------- 航行

void ASubmarine::SetLights(bool bOn)
{
	bFloodlightsOn = bOn;
	for (ULocalLightComponent* L : Floodlights)
	{
		if (L)
		{
			L->SetVisibility(bOn);
		}
	}
}

USceneComponent* ASubmarine::MakePivot(const TCHAR* Name, USceneComponent* Anchor, std::initializer_list<const TCHAR*> Parts)
{
	// 在挂点处建一个转轴，把动件挂上去（保持原位）——Godot 版 _pivot
	if (!Anchor)
	{
		return nullptr;
	}
	USceneComponent* P = UGuixuSceneLibrary::AddComponent<USceneComponent>(this, Anchor->GetAttachParent(), Name);
	P->SetRelativeTransform(Anchor->GetRelativeTransform());
	for (const TCHAR* N : Parts)
	{
		if (USceneComponent* C = Exterior.Find(N))
		{
			C->AttachToComponent(P, FAttachmentTransformRules::KeepWorldTransform);
		}
	}
	return P;
}

void ASubmarine::BuildStern()
{
	PropPivot = MakePivot(TEXT("PropPivot"), Exterior.Find(TEXT("Prop_Axis")), {TEXT("Prop_Main")});
	USceneComponent* Stern = Exterior.Find(TEXT("Pivot_Stern"));
	RudderPivot = MakePivot(TEXT("RudderPivot"), Stern, {TEXT("Fin_RudderU"), TEXT("Fin_RudderD")});
	PlanesPivot = MakePivot(TEXT("PlanesPivot"), Stern, {TEXT("Fin_PlaneL"), TEXT("Fin_PlaneR")});
	RudderBase = RudderPivot ? RudderPivot->GetRelativeRotation().Quaternion() : FQuat::Identity;
	PlanesBase = PlanesPivot ? PlanesPivot->GetRelativeRotation().Quaternion() : FQuat::Identity;
}

void ASubmarine::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	const float Dt = FMath::Min(DeltaTime, 0.1f);
	// 调试：-GuixuCruise=推进（Godot 版 --cruise），不用人坐上去也一直往前开
	static float Cruise = FParse::Value(FCommandLine::Get(), TEXT("-GuixuCruise="), Cruise) ? Cruise : -99.f;
	if (Cruise > -10.f)
	{
		Steering.X = Cruise;
	}
	const float Thrust = Steering.X;
	const float Lift = Steering.Y;
	const float Turn = Steering.Z;

	// 水平：沿艇首推进、水的阻力、限速；竖直：压载升降、阻力大一些
	const FVector Fwd = GetActorForwardVector().GetSafeNormal2D();
	FVector HV(Velocity.X, Velocity.Y, 0.f);
	HV += Fwd * Thrust * ThrustAccel * Dt;
	HV -= HV * WaterDrag * Dt;
	HV = HV.GetClampedToMaxSize(MaxSpeed);
	float VV = Velocity.Z + Lift * VerticalAccel * Dt;
	VV -= VV * WaterDrag * 1.5f * Dt;
	VV = FMath::Clamp(VV, -VerticalMax, VerticalMax);
	Velocity = FVector(HV.X, HV.Y, VV);
	// 漂到几乎停住就停死（停着的时候不写变换，阴影图可以复用）
	if (Velocity.SizeSquared() < 1e-6f && Thrust == 0.f && Lift == 0.f)
	{
		Velocity = FVector::ZeroVector;
	}
	YawSpeedDeg = FMath::FInterpConstantTo(YawSpeedDeg, Turn * TurnMaxDeg, Dt, TurnAccelDeg);
	if (YawSpeedDeg != 0.f)
	{
		// Godot 正的转向是左转（从上往下看逆时针）；UE 正的偏航是顺时针
		AddActorWorldRotation(FRotator(0.f, -YawSpeedDeg * Dt, 0.f));
	}
	if (!Velocity.IsZero())
	{
		MoveHull(Velocity * Dt * 100.f);
	}

	// 艇身随推进、转向轻微俯仰和侧倾（停着不晃）
	const FVector Target(-Thrust * 0.03f + Lift * 0.02f, 0.f, -FMath::DegreesToRadians(YawSpeedDeg) * 0.22f);
	if (!Sway.Equals(Target, 1e-4f))
	{
		Sway = FMath::Lerp(Sway, Target, 1.f - FMath::Exp(-Dt * 1.4f));
		// Godot 的 body.rotation（艇身局部 x 俯仰、z 侧倾）换到 UE：绕 x、绕 y（Godot 的 z），角度取反
		const FQuat SwayQ = FQuat(FVector(1, 0, 0), -Sway.X) * FQuat(FVector(0, 1, 0), -Sway.Z);
		Body->SetRelativeRotation(FQuat(FVector::UpVector, FMath::DegreesToRadians(90.f)) * SwayQ);
	}
	UpdateStern(Dt);
}

void ASubmarine::MoveHull(const FVector& DeltaCm)
{
	// 艇体当一个胶囊扫过去（Godot 版 CapsuleShape3D 半径 1.55、高 14.6，中心在艇身局部 (0, -0.1, 3.85)），碰到海底、礁石就沿表面滑
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	const FQuat Axis = Body->GetComponentQuat() * FQuat(FVector(1, 0, 0), FMath::DegreesToRadians(90.f));  // 胶囊轴沿艇身局部 y（艇长方向）
	const FCollisionShape Shape = FCollisionShape::MakeCapsule(155.f, 730.f);
	FCollisionQueryParams Params(TEXT("SubHull"), false, this);
	FVector Remaining = DeltaCm;
	for (int32 Iter = 0; Iter < 3 && !Remaining.IsNearlyZero(0.01f); ++Iter)
	{
		const FVector Start = Body->GetComponentTransform().TransformPosition(FVector(0.f, 385.f, -10.f));
		FHitResult Hit;
		if (World->SweepSingleByChannel(Hit, Start, Start + Remaining, Axis, ECC_WorldStatic, Shape, Params) && Hit.bBlockingHit && !Hit.bStartPenetrating)
		{
			const FVector Done = Remaining * Hit.Time;
			AddActorWorldOffset(Done - Remaining.GetSafeNormal() * 0.5f);
			const FVector Before = Velocity;
			// 沿碰撞面滑：去掉速度里顶着表面的那部分
			const FVector N = Hit.ImpactNormal;
			Velocity -= N * FMath::Min(0.f, FVector::DotProduct(Velocity, N));
			Remaining = (Remaining - Done) - N * FVector::DotProduct(Remaining - Done, N);
			const float Impact = (Before - Velocity).Size();
			if (Impact > 0.2f)
			{
				OnBumped.Broadcast(Impact);
			}
		}
		else
		{
			AddActorWorldOffset(Remaining);
			Remaining = FVector::ZeroVector;
		}
	}
}

void ASubmarine::UpdateStern(float DeltaTime)
{
	// 螺旋桨跟着推进转；方向舵跟着转向、升降舵跟着上浮下潜偏转（Godot 版 _update_stern）
	if (PropPivot)
	{
		const float Want = Steering.X * 7.f + FVector::DotProduct(Velocity, GetActorForwardVector()) * 0.8f;
		PropSpeed = FMath::FInterpConstantTo(PropSpeed, Want, DeltaTime, 3.f);
		if (FMath::Abs(PropSpeed) > 0.01f)
		{
			// Godot：绕局部 +z 转；换到 UE 是绕局部 +y，角度取反
			PropPivot->AddLocalRotation(FQuat(FVector(0, 1, 0), -PropSpeed * DeltaTime));
		}
	}
	if (RudderPivot)
	{
		const float R = -FMath::Clamp(YawSpeedDeg / TurnMaxDeg, -1.f, 1.f) * FMath::DegreesToRadians(28.f);
		RudderAngle = FMath::Lerp(RudderAngle, R, 1.f - FMath::Exp(-DeltaTime * 3.f));
		RudderPivot->SetRelativeRotation(RudderBase * FQuat(FVector(0, 0, 1), -RudderAngle));
	}
	if (PlanesPivot)
	{
		LiftSmooth = FMath::Lerp(LiftSmooth, Steering.Y, 1.f - FMath::Exp(-DeltaTime * 2.f));
		PlanesPivot->SetRelativeRotation(PlanesBase * FQuat(FVector(1, 0, 0), -LiftSmooth * FMath::DegreesToRadians(20.f)));
	}
}
