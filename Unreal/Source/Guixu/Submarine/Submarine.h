#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Scene/GuixuSceneAsset.h"
#include "Submarine.generated.h"

class UGuixuSceneAsset;
class ULocalLightComponent;
class UInstrumentsComponent;
class USonarComponent;

/**
 * 潜艇（Godot 版 scenes/submarine.tscn + scripts/submarine.gd + cockpit_props.gd 的灯光部分）。
 * 艇体外壳、驾驶舱两个 glb 按节点树搭成组件（Body 下面），舱内灯挂在 CabinLight_* / CabinSpot_* 挂点上，
 * 探照灯挂在 Light_* 挂点上。模型的艇首朝 glTF 的 -Z，Body 转 90° 让艇首朝 Actor 的 +X。
 * 现在只是摆着能进去走；开船、操纵面、螺旋桨、声呐这些后面接着搬。
 */
UCLASS()
class GUIXU_API ASubmarine : public AActor
{
	GENERATED_BODY()

public:
	ASubmarine();

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void Tick(float DeltaTime) override;

	// ---- 航行（Godot 版 submarine.gd 的 _physics_process）：带惯性的推进 / 转向 / 升降，米和秒为单位
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "航行")
	float MaxSpeed = 2.6f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "航行")
	float ThrustAccel = 0.9f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "航行")
	float VerticalMax = 1.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "航行")
	float VerticalAccel = 0.7f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "航行")
	float TurnMaxDeg = 24.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "航行")
	float TurnAccelDeg = 30.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "航行")
	float WaterDrag = 0.45f;

	/** 这一帧的操纵输入：X 推进（-1..1）、Y 升降、Z 转向（正 = 左转），坐在驾驶椅上的船员每帧给 */
	void SetSteering(const FVector& Steer) { Steering = Steer; }
	void SetLights(bool bOn);
	bool AreLightsOn() const { return bFloodlightsOn; }
	void SetSonarActive(bool bActive) { bSonarActive = bActive; }
	bool IsSonarActive() const { return bSonarActive; }
	float Speed() const { return Velocity.Size(); }
	float ThrustInput() const { return Steering.X; }
	float LiftInput() const { return Steering.Y; }
	/** 转向角速度（度/秒，正 = 左转） */
	float YawSpeed() const { return YawSpeedDeg; }

	/** 撞上东西（冲击速度，米/秒）：相机抖、音效、巨物听见 */
	DECLARE_MULTICAST_DELEGATE_OneParam(FOnBumped, float);
	FOnBumped OnBumped;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "潜艇")
	TObjectPtr<UGuixuSceneAsset> ExteriorScene;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "潜艇")
	TObjectPtr<UGuixuSceneAsset> CockpitScene;

	/** Godot 的灯光能量 → UE 的发光强度（坎德拉）。Godot 版没开物理灯光单位，比例靠对着截图调 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "灯光")
	float CabinLightScale = 10.0f;

	/** 探照灯另给一个比例：Godot 版的灯按 1/d^1.2 衰减（非物理），UE 按距离平方衰减，远处的海床要亮起来得把灯整体调亮 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "灯光")
	float FloodlightScale = 40.0f;

	/** 探照灯（Godot 版 light_energy / light_range / light_angle / light_color） */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "灯光")
	float FloodlightEnergy = 22.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "灯光")
	float FloodlightRange = 60.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "灯光")
	float FloodlightAngle = 28.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "灯光")
	FLinearColor FloodlightColor = FLinearColor(1.0f, 0.93f, 0.82f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "灯光")
	bool bFloodlightsOn = true;

	/** 深度（米）：Godot 版 depth_at_origin 减去艇的高度 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "潜艇")
	float DepthAtOrigin = 1850.f;

	/** 按节点名找组件（锚点、灯位、会动的部件），相当于 Godot 的 find_child */
	USceneComponent* FindNode(FName Name) const;

	float Depth() const { return DepthAtOrigin - GetActorLocation().Z / 100.f; }
	/** 航向（度，0 = 关卡的 -Y，也就是 Godot 版的 -Z；顺时针增加） */
	float HeadingDeg() const;
	/** 离底高度（米）：从艇底往正下方打一条线，打不到海底是 -1 */
	float Altitude() const;

	USceneComponent* GetBody() const { return Body; }

private:
	UPROPERTY(VisibleAnywhere, Category = "潜艇")
	TObjectPtr<USceneComponent> Root;

	/** 模型的根：转 90° 让艇首朝 +X */
	UPROPERTY(VisibleAnywhere, Category = "潜艇")
	TObjectPtr<USceneComponent> Body;

	UPROPERTY(VisibleAnywhere, Category = "潜艇")
	TObjectPtr<UInstrumentsComponent> Instruments;

	UPROPERTY(VisibleAnywhere, Category = "潜艇")
	TObjectPtr<USonarComponent> Sonar;

	FGuixuSceneInstance Exterior;
	FGuixuSceneInstance Cockpit;

	UPROPERTY(Transient)
	TArray<TObjectPtr<ULocalLightComponent>> Floodlights;

	FVector Steering = FVector::ZeroVector;
	FVector Velocity = FVector::ZeroVector;   // 米/秒（世界坐标）
	float YawSpeedDeg = 0.f;
	FVector Sway = FVector::ZeroVector;       // 艇身随推进、转向的俯仰和侧倾（弧度，Godot 的 x、z）
	float PropSpeed = 0.f;
	float LiftSmooth = 0.f;
	float RudderAngle = 0.f;
	bool bSonarActive = true;

	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> PropPivot;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> RudderPivot;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> PlanesPivot;
	FQuat RudderBase = FQuat::Identity;
	FQuat PlanesBase = FQuat::Identity;

	void BuildStern();
	USceneComponent* MakePivot(const TCHAR* Name, USceneComponent* Anchor, std::initializer_list<const TCHAR*> Parts);
	void MoveHull(const FVector& DeltaCm);
	void UpdateStern(float DeltaTime);
	void BuildCabinLights();
	void BuildFloodlights();
	void BuildDecals();
	void BuildProps();
};
