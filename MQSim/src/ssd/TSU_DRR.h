#ifndef TSU_DRR_H
#define TSU_DRR_H

#include "TSU_Base.h"
#include "NVM_Transaction_Flash.h"
#include "NVM_PHY_ONFI_NVDDR2.h"
#include "FTL.h"
#include <vector>

namespace SSD_Components
{
class FTL;

class TSU_DRR : public TSU_Base
{
public:
	TSU_DRR(const sim_object_id_type& id,
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
	~TSU_DRR();

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

	// DRR state: per-stream deficit counters and weights
	struct FlowState
	{
		int64_t deficit;
		double weight;
		FlowState() : deficit(0), weight(1.0) {}
	};
	std::vector<FlowState> flow_state_read;   // Per-stream state for reads
	std::vector<FlowState> flow_state_write;  // Per-stream state for writes

	double quantum_;  // Base quantum in bytes (default 4096)
	unsigned int** next_stream_read;   // Per channel/chip: next stream to check for reads
	unsigned int** next_stream_write; // Per channel/chip: next stream to check for writes

	FlowState& get_flow_state_read(stream_id_type sid);
	FlowState& get_flow_state_write(stream_id_type sid);

	bool service_read_transaction(NVM::FlashMemory::Flash_Chip* chip);
	bool service_write_transaction(NVM::FlashMemory::Flash_Chip* chip);
	bool service_erase_transaction(NVM::FlashMemory::Flash_Chip* chip);

	// DRR selection: add quantum, pick transaction that fits deficit
	NVM_Transaction_Flash* pick_next_drr_transaction(Flash_Transaction_Queue& queue, 
													 std::vector<FlowState>& flow_state,
													 unsigned int& next_stream);
};

} // namespace SSD_Components

#endif // TSU_DRR_H

