#include "GuixuGameMode.h"

#include "Crew/CrewCharacter.h"
#include "EngineUtils.h"
#include "Submarine/Submarine.h"

AGuixuGameMode::AGuixuGameMode()
{
	DefaultPawnClass = ACrewCharacter::StaticClass();
}

void AGuixuGameMode::RestartPlayer(AController* NewPlayer)
{
	for (TActorIterator<ASubmarine> It(GetWorld()); It; ++It)
	{
		if (USceneComponent* Stand = It->FindNode(TEXT("Anchor_Stand")))
		{
			// 挂点在地板上：胶囊中心再抬半个身高
			FTransform T = Stand->GetComponentTransform();
			T.SetScale3D(FVector::OneVector);
			T.SetLocation(T.GetLocation() + FVector(0.f, 0.f, 92.f));
			// 面朝艇首
			T.SetRotation(FRotator(0.f, It->GetActorRotation().Yaw, 0.f).Quaternion());
			RestartPlayerAtTransform(NewPlayer, T);
			return;
		}
	}
	Super::RestartPlayer(NewPlayer);
}
