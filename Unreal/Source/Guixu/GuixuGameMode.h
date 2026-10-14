#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GuixuGameMode.generated.h"

/** 先只管单人：开局把船员放进潜艇驾驶舱的 Anchor_Stand（Godot 版开局站的位置） */
UCLASS()
class GUIXU_API AGuixuGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AGuixuGameMode();

	virtual void RestartPlayer(AController* NewPlayer) override;
};
