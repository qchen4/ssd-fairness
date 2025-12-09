#ifndef TSU_RR_H
#define TSU_RR_H

#include "TSU_Base.h"
#include "NVM_Transaction_Flash.h"
#include "NVM_PHY_ONFI_NVDDR2.h"
#include "FTL.h"

namespace SSD_Components
{
class FTL;

class TSU_RR : public TSU_Base
{
public:
	TSU_RR(const sim_object_id_type& id,
		   FTL* ftl,
		   NVM_PHY_ONFI_NVDDR2* NVMController,
		   unsigned int ChannelCount,
		   unsigned int chip_no_per_channel,
		   unsigned int DieNoPerChip,
		   unsigned int PlaneNoPerDie,
		   bool EraseSuspensionEnabled,
		   bool ProgramSuspensionEnabled,
		   sim_time_type WriteReasonableSuspensionTimeForRead,
		   sim_time_type EraseReasonableSuspensionTimeForRead,
		   sim_time_type EraseReasonableSuspensionTimeForWrite);
	~TSU_RR();

	void Schedule();

	void Start_simulation();
	void Validate_simulation_config();
	void Execute_simulator_event(MQSimEngine::Sim_Event* event);
	void Report_results_in_XML(std::string name_prefix, Utils::XmlWriter& xmlwriter);

private:
	Flash_Transaction_Queue** UserReadTRQueue;
	Flash_Transaction_Queue** UserWriteTRQueue;
	Flash_Transaction_Queue** GCReadTRQueue;
	Flash_Transaction_Queue** GCWriteTRQueue;
	Flash_Transaction_Queue** GCEraseTRQueue;
	Flash_Transaction_Queue** MappingReadTRQueue;
	Flash_Transaction_Queue** MappingWriteTRQueue;

	// Round-robin state: track next stream to serve per channel/chip
	// For simplicity, we use a single round-robin counter per channel/chip
	// and cycle through all streams in the queue
	unsigned int** current_stream_read;   // Per channel/chip: current stream index for reads
	unsigned int** current_stream_write;  // Per channel/chip: current stream index for writes

	bool service_read_transaction(NVM::FlashMemory::Flash_Chip* chip);
	bool service_write_transaction(NVM::FlashMemory::Flash_Chip* chip);
	bool service_erase_transaction(NVM::FlashMemory::Flash_Chip* chip);

	// Round-robin selection: pick next transaction from queue in round-robin order
	NVM_Transaction_Flash* pick_next_rr_transaction(Flash_Transaction_Queue& queue, unsigned int& current_stream);
};

} // namespace SSD_Components

#endif // TSU_RR_H

