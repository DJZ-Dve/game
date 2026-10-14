#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GuixuSceneAsset.generated.h"

class UStaticMesh;
class UMaterialInterface;

/** 模型里的一个节点（Blender 生成的 glb 里的物体 / 空物体），变换相对父节点，UE 单位 */
USTRUCT(BlueprintType)
struct FGuixuSceneNode
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Scene")
	FName Name;

	/** 父节点在 Nodes 里的下标，根节点是 -1 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Scene")
	int32 Parent = INDEX_NONE;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Scene")
	FTransform Transform;

	/** 空节点（锚点、灯位、转轴）没有网格 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Scene")
	TObjectPtr<UStaticMesh> Mesh;
};

/**
 * 一个 glb 的节点树（Scripts/import_models.py 导入时生成）。
 * 跟 Godot 版一样按名字找节点：锚点（Anchor_*）、灯位（Light_*、CabinLight_*）、会动的部件（Door_*、Fin_*）……
 * 运行时由 UGuixuSceneLibrary::Build 在某个 Actor 下面搭成组件树。
 */
UCLASS(BlueprintType)
class GUIXU_API UGuixuSceneAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	/** 从哪个 glb 导入的（仓库里的相对路径） */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Scene")
	FString SourceFile;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Scene")
	TArray<FGuixuSceneNode> Nodes;
};

/** 搭好的组件树：按节点名找组件（相当于 Godot 的 find_child） */
USTRUCT(BlueprintType)
struct FGuixuSceneInstance
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Scene")
	TMap<FName, TObjectPtr<USceneComponent>> ByName;

	USceneComponent* Find(FName Name) const
	{
		const TObjectPtr<USceneComponent>* C = ByName.Find(Name);
		return C ? C->Get() : nullptr;
	}

	/** 名字以 Prefix 开头的所有节点（相当于 find_children("Prefix*")），按名字排序 */
	TArray<USceneComponent*> FindPrefix(const FString& Prefix) const;
};

UCLASS()
class GUIXU_API UGuixuSceneLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * 在 Owner 的 Parent 组件下面按节点树建组件：有网格的建 UStaticMeshComponent，空节点建 USceneComponent。
	 * 在 Actor 的 OnConstruction 里调：建出来的算构造脚本组件，编辑器里重新构造时引擎自己清掉，不存进关卡。
	 * 组件名带上 NamePrefix（同一个 Actor 里放两个 glb 时不撞名）。
	 * Keep（给了的话）：有网格的节点只留这些和它们的子孙，留下的挪到父节点原点（Poly Haven 把几个变体并排摆在一个文件里）；
	 * Drop：这些节点连同子孙都不要（Godot 版 cockpit_props.gd 的 keep / drop）。
	 */
	static FGuixuSceneInstance Build(AActor* Owner, USceneComponent* Parent, const UGuixuSceneAsset* Asset, const FString& NamePrefix = FString(),
		const TSet<FName>* Keep = nullptr, const TSet<FName>* Drop = nullptr);

	/** 在 Parent 下面建一个构造脚本组件（灯、碰撞体……），用法同 Build */
	template <class T>
	static T* AddComponent(AActor* Owner, USceneComponent* Parent, FName Name)
	{
		T* Comp = NewObject<T>(Owner, Name);
		Comp->CreationMethod = EComponentCreationMethod::UserConstructionScript;
		Comp->SetupAttachment(Parent);
		Comp->RegisterComponent();
		return Comp;
	}
};
