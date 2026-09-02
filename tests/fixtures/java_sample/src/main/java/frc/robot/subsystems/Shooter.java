package frc.robot.subsystems;

import edu.wpi.first.wpilibj2.command.SubsystemBase;

/** Dual-flywheel shooter that scores game pieces. */
public class Shooter extends SubsystemBase {
  private final TalonFX leftFlywheel = new TalonFX(50);
  private final TalonFX rightFlywheel = new TalonFX(51);
  private final SparkMax feederMotor = new SparkMax(52, MotorType.kBrushless);
}
