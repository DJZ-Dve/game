#include "Guixu.h"

#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "ShaderCore.h"

// 游戏模块：启动时把 Unreal/Shaders/ 映射成着色器虚拟路径 /Guixu，
// 材质的 Custom 节点里就能 #include "/Guixu/xxx.ush"——着色器逻辑写在文本文件里、进 git，好改好对比
// （模块要在 PostConfigInit 阶段加载，见 Guixu.uproject，着色器路径必须在着色器编译系统初始化前注册）
class FGuixuModule : public FDefaultGameModuleImpl
{
public:
	virtual void StartupModule() override
	{
		const FString ShaderDir = FPaths::Combine(FPaths::ProjectDir(), TEXT("Shaders"));
		AddShaderSourceDirectoryMapping(TEXT("/Guixu"), ShaderDir);
	}
};

IMPLEMENT_PRIMARY_GAME_MODULE(FGuixuModule, Guixu, "Guixu");
