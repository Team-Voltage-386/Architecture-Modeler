package frc.robot.subsystems;

import edu.wpi.first.wpilibj2.command.SubsystemBase;

/** Four-module swerve drive. */
public class Drivetrain extends SubsystemBase {
  private final SparkMax frontLeftDrive = new SparkMax(10, MotorType.kBrushless);
  private final SparkMax frontLeftSteer = new SparkMax(11, MotorType.kBrushless);
  private final CANcoder frontLeftEncoder = new CANcoder(12);

  private final SparkMax frontRightDrive = new SparkMax(13, MotorType.kBrushless);
  private final SparkMax frontRightSteer = new SparkMax(14, MotorType.kBrushless);
  private final CANcoder frontRightEncoder = new CANcoder(15);

  private final SparkMax backLeftDrive = new SparkMax(16, MotorType.kBrushless);
  private final SparkMax backLeftSteer = new SparkMax(17, MotorType.kBrushless);
  private final CANcoder backLeftEncoder = new CANcoder(18);

  private final SparkMax backRightDrive = new SparkMax(19, MotorType.kBrushless);
  private final SparkMax backRightSteer = new SparkMax(20, MotorType.kBrushless);
  private final CANcoder backRightEncoder = new CANcoder(21);

  private final Pigeon2 gyro = new Pigeon2(22);
}
