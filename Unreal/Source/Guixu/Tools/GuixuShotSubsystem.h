#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "GuixuShotSubsystem.generated.h"

class ACameraActor;

/**
 * 游戏里截图（Godot 版 tools/capture.py 的 --capture）：命令行带 -GuixuShotJob=任务.json 时启用，
 * 按任务里的机位一个个摆相机、等画面稳定（TSR、Lumen、体积雾都要攒几十帧）、截图，全部截完退出游戏。
 * 机位写法跟 Scripts/render_views.py 一样（at / node / loc）。由 Scripts/ue_shot.py 在后台桌面上跑。
 */
UCLASS()
class GUIXU_API UGuixuShotSubsystem : public UGameInstanceSubsystem, public FTickableGameObject
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UGuixuShotSubsystem, STATGROUP_Tickables); }
	virtual bool IsTickable() const override { return bActive; }
	virtual ETickableTickType GetTickableTickType() const override { return ETickableTickType::Conditional; }
	virtual bool IsTickableWhenPaused() const override { return true; }

private:
	struct FView
	{
		FString Name;
		bool bHasAt = false;
		FVector2D At = FVector2D::ZeroVector;
		FString Node;
		bool bHasLoc = false;
		FVector Loc = FVector::ZeroVector;
		FRotator Rot = FRotator::ZeroRotator;
		float Yaw = 0.f;
		float Pitch = 0.f;
		bool bOrbit = false;      // 舱外环绕视角（Godot 版 external_camera.gd：--orbit / --orbit_pitch / --orbit_dist）
		float OrbitYaw = 145.f;
		float OrbitPitch = -12.f;
		float OrbitDist = 17.f;
		float FovV = -1.f;        // 这个机位自己的竖直视角（舱外 Godot 版是 60°），-1 用任务里的
	};

	bool bActive = false;
	FString JobPath;
	FString OutDir;
	TArray<FView> Views;
	float FovV = 72.f;
	int32 WarmFrames = 300;
	int32 SettleFrames = 90;
	int32 Index = 0;
	int32 Frame = 0;
	int32 Phase = 0;  // 0 等关卡加载、1 摆好机位攒帧、2 已请求截图
	TArray<FString> Results;

	UPROPERTY(Transient)
	TObjectPtr<ACameraActor> Camera;

	/** 舱外视角的补光灯（像一台跟拍的水下机器人自带的灯） */
	UPROPERTY(Transient)
	TObjectPtr<class ASpotLight> Fill;

	bool PlaceCamera(const FView& View);
	void Finish();
};
