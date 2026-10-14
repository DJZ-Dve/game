#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Instruments.generated.h"

class ASubmarine;
class UMaterialInstanceDynamic;
class UStaticMeshComponent;

/**
 * 驾驶舱仪表（Godot 版 scripts/instruments.gd）：指针（弹簧阻尼 + 抖动）、数码管、指示灯、报警灯牌、氧气流量计浮子。
 * 指针由 Blender 生成：原点在转轴上，静止时指在刻度起点，绕局部 y（Godot 坐标）顺时针转 sweep 度到满量程。
 * 声呐屏以后单独搬（Godot 版 sonar_display.gd）。
 */
UCLASS(ClassGroup = (Guixu))
class GUIXU_API UInstrumentsComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UInstrumentsComponent();

	/** 潜艇搭好节点树以后调（ASubmarine::OnConstruction）：找指针、数码管挂点、灯 */
	void Setup(ASubmarine* InSub);

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** 报警灯：0 灭 1 常亮 2 闪烁（Godot 版 Warn 枚举的顺序） */
	void SetWarning(int32 Index, int32 State);

	enum class EWarn : int32 { O2Low, Co2High, Leak, Battery, Insulation, TooDeep, Hydraulic, Comms };

private:
	struct FNeedle
	{
		TWeakObjectPtr<USceneComponent> Node;
		FQuat Base;
		float Sweep = 270.f;
		float Value = 0.f;
		float Vel = 0.f;
	};

	struct FDisplay
	{
		TWeakObjectPtr<UMaterialInstanceDynamic> Mat;
		int32 Cells = 5;
	};

	struct FFloat
	{
		TWeakObjectPtr<USceneComponent> Node;
		FVector Base;
		float Phase = 0.f;
	};

	TWeakObjectPtr<ASubmarine> Sub;
	TMap<FName, FNeedle> Needles;
	TMap<FName, FDisplay> Displays;
	TArray<TWeakObjectPtr<UMaterialInstanceDynamic>> Lamps;
	TArray<TWeakObjectPtr<UMaterialInstanceDynamic>> Warns;
	TArray<int32> WarnState;
	TArray<FFloat> Floats;
	float Battery = 4.6f;
	float Co2 = 0.55f;
	float DiveTime = 0.f;
	float LogKm = 0.f;
	float Time = 0.f;

	void SetGauge(FName Key, float Target, float DeltaTime);
	/** 文本按格写进数码管（右对齐；'.' 不占格，点在前一格的右下角；':' 也不占格） */
	void SetDisplay(FName Key, const FString& Text);
	UMaterialInstanceDynamic* OwnMaterial(USceneComponent* Node) const;
};
