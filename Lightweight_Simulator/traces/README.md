# Trace File Format

The trace files in this directory contain I/O request patterns for the SSD fairness simulator.

## Format
Each line in the CSV file represents a single I/O request with the following fields:
- timestamp: Time of request in microseconds
- process_id: Identifier of the requesting process
- type: Either READ or WRITE
- address: Starting address of the request (in bytes)
- size: Size of the request (in bytes)

## Example
See example.csv for a sample trace file.