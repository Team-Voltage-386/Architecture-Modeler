package frc.robot;

import edu.wpi.first.wpilibj2.command.SubsystemBase;

public class Drive extends SubsystemBase {
  private final SparkMax leftMotor = new SparkMax(4, MotorType.kBrushless);
}
