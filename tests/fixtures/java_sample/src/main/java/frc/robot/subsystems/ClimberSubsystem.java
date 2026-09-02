package frc.robot.subsystems;

import edu.wpi.first.wpilibj2.command.SubsystemBase;

/** Winches the robot up the end-game chain. */
public class ClimberSubsystem extends SubsystemBase {
  private final SparkMax motor = new SparkMax(60, MotorType.kBrushless);
}
