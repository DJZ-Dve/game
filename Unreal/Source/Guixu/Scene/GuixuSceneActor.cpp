#include "Scene/GuixuSceneActor.h"

#include "Components/StaticMeshComponent.h"

AGuixuSceneActor::AGuixuSceneActor()
{
	PrimaryActorTick.bCanEverTick = false;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Static);  // 海床、房间不会动
	RootComponent = Root;
}

void AGuixuSceneActor::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	Instance = UGuixuSceneLibrary::Build(this, Root, Scene);
	PlaceProps();
}

void AGuixuSceneActor::PlaceProps()
{
	// 放置点 Place__素材名__编号（Godot 版 seabed_props.gd；由 blender/scripts/gen_seabed.py 生成）：
	// 在点上摆 Poly Haven 素材（/Game/Props/<素材>/SA_<素材>，Scripts/import_all.py seabed_props 导入），
	// 当声呐的硬目标（回波强、后面有声影，见 Submarine/Sonar.cpp）
	TMap<FString, const UGuixuSceneAsset*> Cache;
	for (USceneComponent* Marker : Instance.FindPrefix(TEXT("Place__")))
	{
		const FString Name = Marker->GetName();
		TArray<FString> Parts;
		Name.ParseIntoArray(Parts, TEXT("__"));
		if (Parts.Num() < 2)
		{
			continue;
		}
		const FString& Asset = Parts[1];
		const UGuixuSceneAsset*& Prop = Cache.FindOrAdd(Asset);
		if (!Prop)
		{
			Prop = LoadObject<UGuixuSceneAsset>(nullptr, *FString::Printf(TEXT("/Game/Props/%s/SA_%s.SA_%s"), *Asset, *Asset, *Asset));
		}
		if (!Prop)
		{
			continue;
		}
		const FGuixuSceneInstance Inst = UGuixuSceneLibrary::Build(this, Marker, Prop, Name + TEXT("_"));
		for (const auto& It : Inst.ByName)
		{
			if (UStaticMeshComponent* M = Cast<UStaticMeshComponent>(It.Value))
			{
				M->ComponentTags.Add(TEXT("SonarHard"));
			}
		}
	}
}
