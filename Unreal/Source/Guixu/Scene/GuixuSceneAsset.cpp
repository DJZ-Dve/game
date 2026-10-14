#include "Scene/GuixuSceneAsset.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Actor.h"

TArray<USceneComponent*> FGuixuSceneInstance::FindPrefix(const FString& Prefix) const
{
	TArray<FName> Names;
	for (const auto& It : ByName)
	{
		if (It.Key.ToString().StartsWith(Prefix))
		{
			Names.Add(It.Key);
		}
	}
	Names.Sort(FNameLexicalLess());
	TArray<USceneComponent*> Out;
	for (const FName& N : Names)
	{
		Out.Add(ByName[N]);
	}
	return Out;
}

FGuixuSceneInstance UGuixuSceneLibrary::Build(AActor* Owner, USceneComponent* Parent, const UGuixuSceneAsset* Asset, const FString& NamePrefix,
	const TSet<FName>* Keep, const TSet<FName>* Drop)
{
	FGuixuSceneInstance Result;
	if (!Owner || !Parent || !Asset)
	{
		return Result;
	}

	const int32 Num = Asset->Nodes.Num();
	TArray<USceneComponent*> Created;
	Created.SetNumZeroed(Num);
	// 节点按父在前的顺序存（导入脚本保证），父节点的标记一遍就能传下去
	TArray<bool> Dropped, UnderKept;
	Dropped.SetNumZeroed(Num);
	UnderKept.SetNumZeroed(Num);
	for (int32 i = 0; i < Num; ++i)
	{
		const FGuixuSceneNode& Node = Asset->Nodes[i];
		const bool bParentOk = Node.Parent >= 0 && Node.Parent < i;
		Dropped[i] = (Drop && Drop->Contains(Node.Name)) || (bParentOk && Dropped[Node.Parent]);
		UnderKept[i] = (Keep && Keep->Contains(Node.Name)) || (bParentOk && UnderKept[Node.Parent]);
	}
	for (int32 i = 0; i < Num; ++i)
	{
		const FGuixuSceneNode& Node = Asset->Nodes[i];
		if (Dropped[i] || (Keep && Node.Mesh && !UnderKept[i]))
		{
			continue;
		}
		const FName CompName(*(NamePrefix + Node.Name.ToString()));
		USceneComponent* Comp = nullptr;
		if (Node.Mesh)
		{
			UStaticMeshComponent* SM = NewObject<UStaticMeshComponent>(Owner, CompName);
			SM->SetStaticMesh(Node.Mesh);
			Comp = SM;
		}
		else
		{
			Comp = NewObject<USceneComponent>(Owner, CompName);
		}
		USceneComponent* AttachTo = (Node.Parent >= 0 && Node.Parent < i && Created[Node.Parent]) ? Created[Node.Parent] : Parent;
		Comp->CreationMethod = EComponentCreationMethod::UserConstructionScript;
		Comp->SetMobility(Parent->Mobility);
		Comp->SetupAttachment(AttachTo);
		FTransform T = Node.Transform;
		if (Keep && Keep->Contains(Node.Name))
		{
			T.SetLocation(FVector::ZeroVector);
		}
		Comp->SetRelativeTransform(T);
		Comp->RegisterComponent();
		Created[i] = Comp;
		Result.ByName.Add(Node.Name, Comp);
	}
	return Result;
}
