using UnrealBuildTool;

public class Guixu : ModuleRules
{
	public Guixu(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		// 源文件按功能分子目录（Scene/、Submarine/……），#include 一律从模块根写起
		PublicIncludePaths.Add(ModuleDirectory);
		PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "Json" });
		// 材质里的 Custom 节点 #include 项目自己的着色器文件（Unreal/Shaders/），要 RenderCore 注册虚拟路径
		PrivateDependencyModuleNames.AddRange(new[] { "RenderCore" });
	}
}
