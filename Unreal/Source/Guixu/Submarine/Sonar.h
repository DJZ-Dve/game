#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Sonar.generated.h"

class ASubmarine;
class UMaterialInstanceDynamic;
class UTexture2D;

/**
 * 驾驶台主动声呐（Godot 版 scripts/sonar_display.gd，扫描式，艏向朝上的 PPI 显示）。
 * 换能器每转一小步发一次声脉冲：往这个方位打一扇从陡到平的射线，命中的海底、礁石按距离写进极坐标回波图的一列
 * （海底连成一片，凸起的东西后面留下声影）；屏幕上的余辉、刻度、显像管质感在材质里算（Shaders/Sonar.ush）。
 * 被动声呐（听方位）、屏上的字、ping 的声音以后搬。
 */
UCLASS(ClassGroup = (Guixu))
class GUIXU_API USonarComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	USonarComponent();

	void Setup(ASubmarine* InSub);

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** 量程（米，面板上档位开关指在 100） */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "声呐")
	float RangeM = 100.f;

	/** 转一圈的秒数 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "声呐")
	float Period = 8.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "声呐")
	float Gain = 1.15f;

	static constexpr int32 Bearings = 256;  // 一圈分多少个方位
	static constexpr int32 Bins = 160;      // 距离分多少格

private:
	TWeakObjectPtr<ASubmarine> Sub;

	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> Returns;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> Screen;

	TArray<uint8> Pixels;  // Bins 行 × Bearings 列，BGRA
	TArray<float> Col;
	TArray<float> Fan;     // 一次发射的射线：往下的斜率（tan），从陡到平
	float Sweep = 0.f;
	int32 NextCol = 0;

	void Ping(int32 Column);
};
