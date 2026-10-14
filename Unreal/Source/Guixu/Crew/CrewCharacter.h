#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "CrewCharacter.generated.h"

class ACameraActor;
class ASpotLight;
class ASubmarine;
class UCameraComponent;
class UInputAction;
class UInputMappingContext;
struct FInputActionValue;

/**
 * 船员（第一人称）。Godot 版是 scripts/cockpit_camera.gd + submarine.gd 的按键：
 * 开局坐在驾驶椅上（WASD 开船、空格 / Ctrl 上浮下潜），E 起身 / 坐下，起身后舱里走动（Shift 跑）；
 * Tab 舱内 / 舱外视角（舱外是环绕艇身的跟拍机位，带一盏补光灯，按住左键拖动转、滚轮远近）；F 探照灯；Q 主动 / 被动声呐。
 * 开门、贴近舷窗、蹚水以后接着搬。按键映射在这里用代码建，不做成资产。
 */
UCLASS()
class GUIXU_API ACrewCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	ACrewCharacter();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void PawnClientRestart() override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "船员")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "船员")
	float WalkSpeed = 140.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "船员")
	float RunSpeed = 300.f;

	/** 鼠标灵敏度（度 / 像素） */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "船员")
	float LookSensitivity = 0.12f;

	/** 开局坐在驾驶椅上（Godot 版也是） */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "船员")
	bool bStartSeated = true;

	bool IsSeated() const { return bSeated; }

private:
	UPROPERTY(Transient)
	TObjectPtr<UInputMappingContext> Mapping;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> MoveAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LookAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> RunAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LiftAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> InteractAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ViewAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LightsAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SonarAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> OrbitDragAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ZoomAction;

	TWeakObjectPtr<ASubmarine> Sub;
	bool bSeated = false;
	FVector2D MoveInput = FVector2D::ZeroVector;
	float LiftInput = 0.f;
	float SeatYaw = 0.f;    // 坐着时相对驾驶椅朝向的转头（度）
	float SeatPitch = 0.f;

	// 舱外视角（Godot 版 external_camera.gd）
	bool bExternal = false;
	bool bOrbitDrag = false;
	float OrbitYaw = 145.f;
	float OrbitPitch = -12.f;
	float OrbitDist = 17.f;
	UPROPERTY(Transient)
	TObjectPtr<ACameraActor> ExternalCamera;
	UPROPERTY(Transient)
	TObjectPtr<ASpotLight> ExternalFill;

	void BuildInput();
	ASubmarine* FindSub();
	void Move(const FInputActionValue& Value);
	void MoveStop(const FInputActionValue& Value);
	void Look(const FInputActionValue& Value);
	void Lift(const FInputActionValue& Value);
	void LiftStop(const FInputActionValue& Value);
	void RunStart();
	void RunStop();
	void Interact();
	void ToggleView();
	void ToggleLights();
	void ToggleSonar();
	void OrbitDragStart() { bOrbitDrag = true; }
	void OrbitDragStop() { bOrbitDrag = false; }
	void Zoom(const FInputActionValue& Value);

	void Sit();
	void Stand();
	void UpdateSeat();
	void UpdateExternal();
};
