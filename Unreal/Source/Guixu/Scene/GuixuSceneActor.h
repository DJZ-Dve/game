#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Scene/GuixuSceneAsset.h"
#include "GuixuSceneActor.generated.h"

/** 把一个 glb 的节点树原样摆出来的 Actor（海床、岸上的房间……）。节点按名字找：Instance.Find */
UCLASS()
class GUIXU_API AGuixuSceneActor : public AActor
{
	GENERATED_BODY()

public:
	AGuixuSceneActor();

	virtual void OnConstruction(const FTransform& Transform) override;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Scene")
	TObjectPtr<UGuixuSceneAsset> Scene;

	FGuixuSceneInstance Instance;

private:
	/** 节点树里的 Place__素材名__编号 点上摆 Poly Haven 素材 */
	void PlaceProps();

	UPROPERTY(VisibleAnywhere, Category = "Scene")
	TObjectPtr<USceneComponent> Root;
};
