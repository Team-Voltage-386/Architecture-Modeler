package frc.robot.subsystems;

import edu.wpi.first.wpilibj2.command.SubsystemBase;

/** Vertical elevator that raises the shooter to scoring height. */
public class Elevator extends SubsystemBase {
  private final SparkMax leaderMotor = new SparkMax(40, MotorType.kBrushless);
  private final SparkMax followerMotor = new SparkMax(41, MotorType.kBrushless);
  private final DigitalInput lowerLimitSwitch = new DigitalInput(1);
}
