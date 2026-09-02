package frc.robot.subsystems;

import edu.wpi.first.wpilibj2.command.SubsystemBase;

/** Ground intake that picks up game pieces and feeds them to the shooter. */
public class Intake extends SubsystemBase {
  private final SparkMax motor = new SparkMax(30, MotorType.kBrushless);
  private final DigitalInput noteSensor = new DigitalInput(0);
}
